package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"time"

	"golang.org/x/sync/singleflight"

	"github.com/gin-gonic/gin"
	"github.com/qdrant/go-client/qdrant"
)

const OAUTH_URL string = "http://10.63.0.110:8000/oauth/"
const EMB_URL string = "http://10.63.0.110:8000/embeddings"
const COLLECTION = "bioforge-kb"

type EmbeddingData struct {
	Embedding []float32      `json:"embedding"`
	Object    string         `json:"object"`
	Usage     map[string]int `json:"usage"`
}

type Request struct {
	Data   []EmbeddingData `json:"data"`
	Model  string          `json:"model"`
	Object string          `json:"object"`
}

type ExecuteRequest struct {
	Code string `json:"code"`
}

type SaveRequest struct {
	ID     uint64 `json:"id"`     // client can set or generate
	Result string `json:"result"` // результат работы интерпретатора
}

var (
	token       string
	tokenExpiry time.Time
	mu          sync.Mutex
	g           singleflight.Group
)

func main() {
	router := gin.Default()

	router.Static("/home", "./assets")

	// клиент qdrant
	qclient, err := qdrant.NewClient(&qdrant.Config{
		Host: os.Getenv("QDRANT_HOST"),
		Port: 6334,
	})
	if err != nil {
		log.Fatal(err)
	}

	router.POST("/api/execute", func(c *gin.Context) {
		var req ExecuteRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		tmpfile, err := os.CreateTemp("/tmp", "genlang-*.gl")
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		defer os.Remove(tmpfile.Name())

		if _, err := tmpfile.WriteString(req.Code); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		tmpfile.Close()

		// запуск интерпретатора genlang
		cmd := exec.Command("/srv/genlang", tmpfile.Name())
		cmd.Env = os.Environ()
		result, err := cmd.CombinedOutput()
		if err != nil {
			fmt.Println(err)
			c.JSON(http.StatusInternalServerError, gin.H{"error": string(result)})
			return
		}

		c.JSON(200, gin.H{"result": string(result)})
	})

	// POST /api/save
	router.POST("/api/save", func(c *gin.Context) {
		var req SaveRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		// parse result to extract Express Real
		lines := strings.Split(req.Result, "\n")
		var realResult string
		for _, line := range lines {
			if strings.HasPrefix(strings.TrimSpace(line), "Express Real:") {
				realResult = strings.TrimSpace(strings.TrimPrefix(line, "Express Real:"))
				break
			}
		}
		if realResult == "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "no Express Real found"})
			return
		}

		var embedding []float32
		if strings.HasPrefix(realResult, "flag{") {
			embedding = make([]float32, 1024)
			embedding[0] = 13.37
			embedding[1] = 0.42

		} else {
			embedding, err = getEmbeddings(realResult)
			if err != nil {
				c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
				return
			}
		}
		_, err = qclient.Upsert(context.Background(), &qdrant.UpsertPoints{
			CollectionName: COLLECTION,
			Points: []*qdrant.PointStruct{
				{
					Id:      qdrant.NewIDNum(uint64(req.ID)),
					Vectors: qdrant.NewVectors(embedding...),
					Payload: qdrant.NewValueMap(map[string]any{
						"result": req.Result,
					}),
				},
			},
		})
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		c.JSON(200, gin.H{"status": "ok", "id": req.ID})
	})
	// GET /api/results/:id
	router.GET("/api/results/:id", func(c *gin.Context) {
		idStr := c.Param("id")
		id, err := strconv.Atoi(idStr)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "bad id"})
			return
		}

		pt, err := qclient.Get(context.Background(), &qdrant.GetPoints{
			CollectionName: COLLECTION,
			Ids: []*qdrant.PointId{
				qdrant.NewIDNum(uint64(id)),
			},
			WithPayload: qdrant.NewWithPayload(true),
		})
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		if len(pt) == 0 {
			c.JSON(404, gin.H{"error": "no such id"})
			return
		}
		c.JSON(200, pt)
	})

	router.Run(":8080")
}

func getOauthToken() (string, error) {
	mu.Lock()
	if token != "" && time.Now().Before(tokenExpiry) {
		defer mu.Unlock()
		return token, nil
	}
	mu.Unlock()
	v, err, _ := g.Do("token", func() (any, error) {
		resp, err := http.Post(OAUTH_URL, "application/json", nil)
		if err != nil {
			return "", err
		}
		defer resp.Body.Close()
		var res map[string]any
		json.NewDecoder(resp.Body).Decode(&res)
		newToken := res["access_token"].(string)
		mu.Lock()
		token = newToken
		tokenExpiry = time.Now().Add(3 * time.Minute)
		mu.Unlock()
		return newToken, nil
	})
	if err != nil {
		return "", err
	}
	return v.(string), nil
}

func getEmbeddings(genomeSeq string) ([]float32, error) {
	payload := map[string]string{
		"model": "Embeddings",
		"input": genomeSeq,
	}
	pl, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	client := &http.Client{}
	req, err := http.NewRequest("POST", EMB_URL, bytes.NewReader(pl))
	if err != nil {
		return nil, err
	}
	token, err := getOauthToken()
	if err != nil {
		return nil, err
	}
	req.Header.Add("Content-Type", "application/json")
	req.Header.Add("Accept", "application/json")
	req.Header.Add("Authorization", "Bearer "+token)

	res, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	var reqs_e Request
	err = json.NewDecoder(res.Body).Decode(&reqs_e)
	if err != nil {
		return nil, err
	}
	return reqs_e.Data[0].Embedding, nil
}
