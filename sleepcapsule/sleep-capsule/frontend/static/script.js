class SleepCapsuleApp {
    constructor() {
        this.currentUser = null;
        this.currentCapsule = null;
        this.userCapsules = [];
        this.apiBase = '/api';
        this.init();
    }

    init() {
        this.bindEvents();
        this.checkAuth();
        this.updateUserSection();
    }

    bindEvents() {
        document.getElementById('loginBtn')?.addEventListener('click', () => this.showAuthScreen('login'));
        document.getElementById('registerBtn')?.addEventListener('click', () => this.showAuthScreen('register'));
        document.getElementById('switchAuth').addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleAuthMode();
        });
        document.getElementById('authForm').addEventListener('submit', (e) => this.handleAuth(e));

        document.getElementById('addCapsuleBtn').addEventListener('click', () => this.showCreateCapsuleModal());
        document.getElementById('createFirstCapsule').addEventListener('click', () => this.showCreateCapsuleModal());
        document.getElementById('createCapsuleForm').addEventListener('submit', (e) => this.createCapsule(e));
        
        document.getElementById('backToCapsules').addEventListener('click', () => this.showCapsulesScreen());

        document.getElementById('controlForm').addEventListener('submit', (e) => this.updateCapsuleParams(e));
        document.getElementById('createClusterForm').addEventListener('submit', (e) => this.createCluster(e));
        document.getElementById('joinClusterForm').addEventListener('submit', (e) => this.sendJoinRequest(e));

        document.querySelector('#createCapsuleModal .close').addEventListener('click', () => this.closeModal());
    }

    updateUserSection() {
        const userSection = document.getElementById('userSection');
        if (this.currentUser) {
            userSection.innerHTML = `
                <span>Привет, ${this.currentUser.username}!</span>
                <button id="logoutBtn" class="cosmic-btn">Выйти</button>
            `;
            document.getElementById('logoutBtn').addEventListener('click', () => this.logout());
        } else {
            userSection.innerHTML = `
                <button id="loginBtn" class="cosmic-btn">Войти</button>
                <button id="registerBtn" class="cosmic-btn">Регистрация</button>
            `;
            document.getElementById('loginBtn').addEventListener('click', () => this.showAuthScreen('login'));
            document.getElementById('registerBtn').addEventListener('click', () => this.showAuthScreen('register'));
        }
    }

    async checkAuth() {
        const token = localStorage.getItem('token');
        if (token) {
            try {
                const response = await fetch(`${this.apiBase}/user/me`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (response.ok) {
                    this.currentUser = await response.json();
                    this.updateUserSection();
                    this.showCapsulesScreen();
                    await this.loadUserCapsules();
                }
            } catch (error) {
                console.error('Auth check failed:', error);
                localStorage.removeItem('token');
                this.showAuthScreen('login');
            }
        } else {
            this.showAuthScreen('login');
        }
    }

    showScreen(screenName) {
        document.querySelectorAll('.screen').forEach(screen => {
            screen.classList.remove('active');
        });
        
        document.getElementById(screenName).classList.add('active');
    }

    showAuthScreen(mode) {
        this.showScreen('authScreen');
        this.setAuthMode(mode);
        this.updateUserSection();
    }

    showCapsulesScreen() {
        this.showScreen('capsulesScreen');
        this.updateUserSection();
        this.loadUserCapsules();
        this.loadClusters();
    }

    showCapsuleDetailScreen(capsule) {
        if (capsule.status === 'destroyed') {
            this.showDestroyedCapsule(capsule);
        } else {
            this.currentCapsule = capsule;
            this.showScreen('capsuleDetailScreen');
            this.updateCapsuleDetailDisplay();
            this.loadClusterData();
            this.loadClusterRequests();
        }
    }

    setAuthMode(mode) {
        const title = document.getElementById('authTitle');
        const submitBtn = document.querySelector('#authForm button');
        const switchText = document.getElementById('authSwitch');
        
        if (mode === 'register') {
            title.textContent = 'Регистрация';
            submitBtn.textContent = 'Зарегистрироваться';
            switchText.innerHTML = 'Уже есть аккаунт? <a href="#" id="switchAuth">Войти</a>';
        } else {
            title.textContent = 'Вход в систему';
            submitBtn.textContent = 'Войти';
            switchText.innerHTML = 'Нет аккаунта? <a href="#" id="switchAuth">Зарегистрироваться</a>';
        }
        
        document.getElementById('authForm').dataset.mode = mode;
    }

    toggleAuthMode() {
        const currentMode = document.getElementById('authForm').dataset.mode;
        this.setAuthMode(currentMode === 'login' ? 'register' : 'login');
    }

    async handleAuth(e) {
        e.preventDefault();
        const form = e.target;
        const formData = new FormData(form);
        const mode = e.target.dataset.mode;
        
        const data = {
            username: formData.get('username'),
            password: formData.get('password')
        };

        try {
            const response = await fetch(`${this.apiBase}/auth/${mode}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                const result = await response.json();
                localStorage.setItem('token', result.access_token);
                this.currentUser = result.user;
                this.updateUserSection();
                this.showCapsulesScreen();
                await this.loadUserCapsules();
                form.reset();
            } else {
                const errorData = await response.json();
                this.showError(errorData.detail || 'Ошибка авторизации');
            }
        } catch (error) {
            this.showError('Ошибка сети');
        }
    }

    async loadUserCapsules() {
        try {
            const response = await fetch(`${this.apiBase}/capsule`, {
                headers: this.getAuthHeaders()
            });
            
            if (response.ok) {
                this.userCapsules = await response.json();
                this.updateCapsulesList();
            }
        } catch (error) {
            console.error('Failed to load capsules:', error);
        }
    }

    async loadClusters() {
        try {
            const response = await fetch(`${this.apiBase}/cluster`, {
                headers: this.getAuthHeaders()
            });
            
            if (response.ok) {
                this.clusters = await response.json();
                this.updateClusterList();
            }
        } catch (error) {
            console.error('Failed to load clusters:', error);
        }
    }

    updateCapsulesList() {
        const capsulesList = document.getElementById('capsulesList');
        const noCapsulesMessage = document.getElementById('noCapsulesMessage');

        if (this.userCapsules.length === 0) {
            capsulesList.style.display = 'none';
            noCapsulesMessage.style.display = 'block';
            return;
        }

        capsulesList.style.display = 'grid';
        noCapsulesMessage.style.display = 'none';

        capsulesList.innerHTML = this.userCapsules.map((capsule, index) => `
            <div class="capsule-card cosmic-card" onclick="app.showCapsuleDetailScreen(${this.escapeCapsule(capsule)})">
                <div id="capsule-${index}" class="capsule-name"></div>
                <div class="capsule-stats">
                    <div class="capsule-stat">
                        <label>Температура</label>
                        <span>${capsule.temperature}°C</span>
                    </div>
                    <div class="capsule-stat">
                        <label>Кислород</label>
                        <span>${capsule.oxygen_level}%</span>
                    </div>
                </div>
                <div class="capsule-status ${capsule.status === 'day' ? 'status-day' : 'status-night'}">
                    ${capsule.status === 'day' ? 'День' : 'Ночь'}
                </div>
            </div>
        `).join('');

        for (let index = 0; index < this.userCapsules.length; index++) {
            const capsuleElement = document.getElementById(`capsule-${index}`);

            if (capsuleElement) {
                capsuleElement.textContent = `${this.userCapsules[index].name}`;
            }
        }
    }

    updateClusterList() {
        const clusterList = document.getElementById('clusterList');
        clusterList.innerHTML = this.clusters.map((cluster, index) => `
            <div class="cosmic-card">
                <div id="cluster-${index}" class="capsule-name"></div>
            </div>
        `).join('');

        for (let index = 0; index < this.clusters.length; index++) {
            const clusterElement = document.getElementById(`cluster-${index}`);

            if (clusterElement) {
                clusterElement.textContent = `${this.clusters[index].name}`;
            }
        }
    }

    showDestroyedCapsule(capsule) {
        this.showDestroyedModal();
    }

    showDestroyedModal() {
        const modal = document.getElementById('destroyedModal');
        modal.style.display = 'block';
    }

    escapeCapsule(capsule) {
        return JSON.stringify(capsule).replace(/"/g, '&quot;');
    }

    showCreateCapsuleModal() {
        document.getElementById('createCapsuleModal').style.display = 'block';
    }

    closeModal() {
        document.getElementById('createCapsuleModal').style.display = 'none';
    }

    async createCapsule(e) {
        e.preventDefault();
        const form = e.target;
        const formData = new FormData(form);
        
        const capsuleCode = formData.get('newCapsuleCode');
        const confirmCode = formData.get('confirmCapsuleCode');
        
        if (capsuleCode !== confirmCode) {
            this.showError('Коды доступа не совпадают');
            return;
        }

        const data = {
            name: formData.get('newCapsuleName'),
            access_code: capsuleCode
        };

        try {
            const response = await fetch(`${this.apiBase}/capsule`, {
                method: 'POST',
                headers: { ...this.getAuthHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                this.showSuccess('Капсула успешно создана!');
                this.closeModal();
                form.reset();
                await this.loadUserCapsules();
            } else {
                const errorData = await response.json();
                this.showError(errorData.detail || 'Ошибка создания капсулы');
            }
        } catch (error) {
            this.showError('Ошибка сети');
        }
    }

    updateCapsuleDetailDisplay() {
        if (!this.currentCapsule) return;

        document.getElementById('capsuleDetailTitle').textContent = `${this.currentCapsule.name}`;
        document.getElementById('detailCapsuleName').textContent = this.currentCapsule.name;
        document.getElementById('detailTemperature').textContent = `${this.currentCapsule.temperature}°C`;
        document.getElementById('detailOxygen').textContent = `${this.currentCapsule.oxygen_level}%`;
        document.getElementById('detailStatus').textContent = this.currentCapsule.status === 'day' ? 'День' : 'Ночь';

        if (this.currentCapsule.status === 'night') {
            document.body.classList.add('night-mode');
        } else {
            document.body.classList.remove('night-mode');
        }
    }

    async updateCapsuleParams(e) {
        e.preventDefault();
        const accessCode = prompt(`Введите код доступа для капсулы:`);
        if (!accessCode) return;

        const form = e.target;
        const formData = new FormData(form);
        
        const updates = {};
        if (formData.get('statusSelect')) updates.status = formData.get('statusSelect');
        if (formData.get('tempInput')) updates.temperature = parseInt(formData.get('tempInput'));
        if (formData.get('oxygenInput')) updates.oxygen_level = parseInt(formData.get('oxygenInput'));

        try {
            const response = await fetch(`${this.apiBase}/capsule/${this.currentCapsule.id}`, {
                method: 'PUT',
                headers: { ...this.getAuthHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...updates, access_code: accessCode })
            });

            if (response.ok) {
                this.showSuccess('Параметры обновлены!');
                await this.loadUserCapsules();

                const updatedCapsule = await response.json();
                this.currentCapsule = updatedCapsule;
                this.updateCapsuleDetailDisplay();
                form.reset();
            } else {
                const errorData = await response.json();
                this.showError(errorData.detail || 'Ошибка обновления параметров');
            }
        } catch (error) {
            this.showError('Ошибка сети');
        }
    }

    async createCluster(e) {
        e.preventDefault();
        const accessCode = prompt(`Введите код доступа для капсулы:`);
        if (!accessCode) return;

        const form = e.target;
        const formData = new FormData(form);
        const clusterName = formData.get('clusterNameInput');
        const clusterKey = formData.get('clusterKeyInput');

        try {
            const response = await fetch(`${this.apiBase}/capsule/${this.currentCapsule.id}/cluster-key`, {
                method: 'POST',
                headers: { ...this.getAuthHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    access_code: accessCode,
                    cluster_name: clusterName,
                    cluster_key: clusterKey
                })
            });

            if (response.ok) {
                const result = await response.json();
                this.showSuccess(`Кластер создан: ${result.cluster_name}`);
                form.reset();
                await this.loadUserCapsules();
                await this.loadClusterData();

                this.currentCapsule.cluster_name = result.cluster_name;
                this.currentCapsule.cluster_key = result.cluster_key;
                this.updateCapsuleDetailDisplay();
            } else {
                const errorData = await response.json();
                this.showError(errorData.detail || 'Ошибка создания кластера');
            }
        } catch (error) {
            this.showError('Ошибка сети');
        }
    }

    async loadClusterData() {
        if (!this.currentCapsule) return;
        
        try {
            const response = await fetch(`${this.apiBase}/capsule/${this.currentCapsule.id}/cluster`, {
                headers: this.getAuthHeaders()
            });
            
            if (response.ok) {
                const cluster = await response.json();
                this.updateClusterDisplay(cluster);
            } else {
                this.updateClusterDisplay(null);
            }
        } catch (error) {
            console.error('Failed to load cluster data:', error);
            this.updateClusterDisplay(null);
        }
    }

    updateClusterDisplay(cluster) {
        const clusterInfo = document.getElementById('clusterInfo');
        if (cluster) {
            document.getElementById('create-cluster-div').style.display = 'none';
            document.getElementById('join-cluster-div').style.display = 'none';
            document.getElementById('cluster-info-div').style.display = 'block';
            clusterInfo.innerHTML = `
                <p><strong>Название:</strong></p><p id="cluster-display-name"></p>
                <p><strong>Ключ:</strong></p><p id="cluster-display-key"></p>
                <p><strong>Участников:</strong> ${cluster.members_count}</p>
                <div class="cluster-members">
                    <h5>Участники кластера:</h5>
                    ${cluster.members.map((member, index) => `
                        <div class="cluster-member">
                            <span id="cluster-member-${index}"></span>
                            <span>${member.temperature}°C</span>
                            <span>${member.oxygen_level}%</span>
                            <span>${member.status === 'day' ? 'День' : 'Ночь'}</span>
                        </div>
                    `).join('')}
                </div>
            `;

            document.getElementById('cluster-display-name').textContent = ` ${cluster.cluster_name}`;
            document.getElementById('cluster-display-key').textContent = ` ${cluster.cluster_key}`;

            for (let index = 0; index < cluster.members.length; index++) {
                const memberElement = document.getElementById(`cluster-member-${index}`);

                if (memberElement) {
                    memberElement.textContent = ` ${cluster.members[index].name}`;
                }
            }
        } else {
            document.getElementById('create-cluster-div').style.display = 'block';
            document.getElementById('join-cluster-div').style.display = 'block';
            document.getElementById('cluster-info-div').style.display = 'none';
        }
    }

    async sendJoinRequest(e) {
        e.preventDefault();
        const accessCode = prompt(`Введите код доступа для капсулы:`);
        if (!accessCode) return;

        const form = e.target;
        const formData = new FormData(form);
        const clusterName = formData.get('joinClusterName');

        try {
            const response = await fetch(`${this.apiBase}/capsule/${this.currentCapsule.id}/cluster/join`, {
                method: 'POST',
                headers: { ...this.getAuthHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cluster_name: clusterName,
                    access_code: accessCode
                })
            });

            if (response.ok) {
                this.showSuccess('Запрос на объединение отправлен!');
                form.reset();
            } else {
                const errorData = await response.json();
                this.showError(errorData.detail || 'Ошибка отправки запроса');
            }
        } catch (error) {
            this.showError('Ошибка сети');
        }
    }

    async loadClusterRequests() {
        try {
            const response = await fetch(`${this.apiBase}/capsule/${this.currentCapsule.id}/cluster/requests`, {
                headers: this.getAuthHeaders()
            });
            
            if (response.ok) {
                const requests = await response.json();
                this.updateRequestsDisplay(requests);
            }
        } catch (error) {
            console.error('Failed to load requests:', error);
        }
    }

    updateRequestsDisplay(requests) {
        const requestsList = document.getElementById('requestsList');
        if (requests.length === 0) {
            requestsList.innerHTML = '<p>Нет активных запросов</p>';
            return;
        }

        requestsList.innerHTML = requests.map((request, index) => `
            <div class="request-item">
                <p><strong>Запрос от:</strong></p><p id="sender-${index}"></p>
                <p><strong>К вашему кластеру:</strong></p><p id="cluster-${index}"></p>
                <div class="request-actions">
                    <button onclick="app.handleClusterRequest('${request.receiver_capsule_name}', '${request.sender_capsule_name}', 'approve')" 
                            class="cosmic-btn primary">Принять</button>
                    <button onclick="app.handleClusterRequest('${request.receiver_capsule_name}', '${request.sender_capsule_name}', 'reject')" 
                            class="cosmic-btn">Отклонить</button>
                </div>
            </div>
        `).join('');

        for (let index = 0; index < requests.length; index++) {
            const senderElement = document.getElementById(`sender-${index}`);
            const clusterElement = document.getElementById(`cluster-${index}`);

            if (senderElement) {
                senderElement.textContent = ` ${requests[index].sender_capsule_name}`;
            }

            if (clusterElement) {
                clusterElement.textContent = ` ${requests[index].cluster_name}`;
            }
        }
    }

    async handleClusterRequest(capsuleMain, capsuleGuest, action) {
        const accessCode = prompt(`Введите код доступа для капсулы:`);
        if (!accessCode) return;

        try {
            const url = `${this.apiBase}/cluster-requests/${capsuleMain}/${action === 'approve' ? 'approve' : 'reject'}/${capsuleGuest}`;
            const response = await fetch(url, {
                method: 'POST',
                headers: { ...this.getAuthHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ access_code: accessCode })
            });

            if (response.ok) {
                this.showSuccess(`Запрос ${action === 'approve' ? 'принят' : 'отклонен'}`);
                await this.loadClusterData();
                await this.loadClusterRequests();
            } else {
                const errorData = await response.json();
                this.showError(errorData.detail || 'Ошибка обработки запроса');
            }
        } catch (error) {
            this.showError('Ошибка сети');
        }
    }

    getAuthHeaders() {
        const token = localStorage.getItem('token');
        return token ? { 'Authorization': `Bearer ${token}` } : {};
    }

    showSuccess(message) {
        alert(`✅ ${message}`);
    }

    showError(message) {
        alert(`❌ ${message}`);
    }

    logout() {
        localStorage.removeItem('token');
        this.currentUser = null;
        this.currentCapsule = null;
        this.userCapsules = [];
        this.showAuthScreen('login');
        document.body.classList.remove('night-mode');
    }
}

const app = new SleepCapsuleApp();

function closeDestroyedModal() {
    const modal = document.getElementById('destroyedModal');
    modal.style.display = 'none';
}