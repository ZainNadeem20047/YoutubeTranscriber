document.addEventListener('DOMContentLoaded', () => {
    // Auth Elements
    const authOverlay = document.getElementById('authOverlay');
    const appLayout = document.getElementById('appLayout');
    const authForm = document.getElementById('authForm');
    const authTitle = document.getElementById('authTitle');
    const logoutBtn = document.getElementById('logoutBtn');
    const userNameDisplay = document.getElementById('userNameDisplay');
    const authCardMain = document.getElementById('authCardMain');
    const authCardOtp = document.getElementById('authCardOtp');
    const otpForm = document.getElementById('otpForm');
    const authOtp = document.getElementById('authOtp');
    const authEmail = document.getElementById('authEmail');
    const authPassword = document.getElementById('authPassword');
    const authConfirmPassword = document.getElementById('authConfirmPassword');
    const confirmPasswordBox = document.getElementById('confirmPasswordBox');
    const btnBackToAuth = document.getElementById('btnBackToAuth');
    
    // Settings Elements
    const settingsOverlay = document.getElementById('settingsOverlay');
    const btnOpenSettings = document.getElementById('btnOpenSettings');
    const btnCancelSettings = document.getElementById('btnCancelSettings');
    const settingsForm = document.getElementById('settingsForm');
    const geminiApiKey = document.getElementById('geminiApiKey');

    // Main DOM Elements
    const form = document.getElementById('transcribeForm');
    const urlInput = document.getElementById('youtubeUrl');
    const heroSection = document.getElementById('heroSection');
    const processingState = document.getElementById('processingState');
    const processingText = document.getElementById('processingText');
    const resultsCard = document.getElementById('resultsCard');
    const historyList = document.getElementById('historyList');
    const newTranscribeBtn = document.getElementById('newTranscribeBtn');
    const themeToggle = document.getElementById('themeToggle');
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');
    
    // Tabs & Content
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    const summaryList = document.getElementById('summaryList');
    const summaryActionArea = document.getElementById('summaryActionArea');
    const generateSummaryBtn = document.getElementById('generateSummaryBtn');
    const transcriptText = document.getElementById('transcriptText');
    const copyBtn = document.getElementById('copyBtn');
    
    // Translation Elements
    const targetLanguage = document.getElementById('targetLanguage');
    const btnTranslate = document.getElementById('btnTranslate');

    const updateTextDirection = () => {
        const lang = targetLanguage.value;
        const isRTL = lang === 'ur' || lang === 'ar';
        const tabContentContainer = document.querySelector('.tab-content');
        if (tabContentContainer) {
            tabContentContainer.setAttribute('dir', isRTL ? 'rtl' : 'ltr');
            tabContentContainer.style.textAlign = isRTL ? 'right' : 'left';
        }
    };
    targetLanguage.addEventListener('change', updateTextDirection);

    let currentVideoId = null;
    let isSignUpMode = false;

    let pendingEmail = '';

    // --- Settings UI ---
    btnOpenSettings.addEventListener('click', () => {
        settingsOverlay.classList.remove('hidden');
        geminiApiKey.value = localStorage.getItem('gemini_api_key') || '';
    });
    btnCancelSettings.addEventListener('click', () => {
        settingsOverlay.classList.add('hidden');
    });
    settingsForm.addEventListener('submit', (e) => {
        e.preventDefault();
        localStorage.setItem('gemini_api_key', geminiApiKey.value.trim());
        settingsOverlay.classList.add('hidden');
        showToast("Settings saved securely.", "success");
    });

    // --- Authentication ---
    const checkAuth = () => {
        const token = localStorage.getItem('auth_token');
        if(token) {
            authOverlay.classList.add('hidden');
            appLayout.style.filter = 'none';
            appLayout.style.pointerEvents = 'all';
            userNameDisplay.textContent = localStorage.getItem('auth_email') || 'User';
            fetchHistory();
        } else {
            authOverlay.classList.remove('hidden');
            appLayout.style.filter = 'blur(5px)';
            appLayout.style.pointerEvents = 'none';
            authCardMain.classList.remove('hidden');
            authCardOtp.classList.add('hidden');
        }
    };

    const rebindAuthSwitch = () => {
        document.getElementById('authSwitchBtn').addEventListener('click', (e) => {
            e.preventDefault();
            isSignUpMode = !isSignUpMode;
            if(isSignUpMode) {
                authTitle.textContent = "Create Account";
                document.querySelector('.auth-switch').innerHTML = `Already have an account? <a href="#" id="authSwitchBtn">Sign in</a>`;
                confirmPasswordBox.classList.remove('hidden');
                authConfirmPassword.required = true;
            } else {
                authTitle.textContent = "Sign In";
                document.querySelector('.auth-switch').innerHTML = `Don't have an account? <a href="#" id="authSwitchBtn">Sign up</a>`;
                confirmPasswordBox.classList.add('hidden');
                authConfirmPassword.required = false;
            }
            rebindAuthSwitch();
        });
    }
    rebindAuthSwitch();

    authForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = authEmail.value.trim();
        const password = authPassword.value;
        const confirmPassword = authConfirmPassword.value;
        
        if (isSignUpMode && password !== confirmPassword) {
            showError("Passwords do not match.");
            return;
        }
        
        const endpoint = isSignUpMode ? '/api/auth/register' : '/api/auth/login';
        
        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password})
            });
            const data = await res.json();
            
            if(res.ok) {
                pendingEmail = email;
                authCardMain.classList.add('hidden');
                authCardOtp.classList.remove('hidden');
                if (isSignUpMode) {
                    showToast(`OTP sent to ${email} (Check server console for demo)`, "success");
                } else {
                    showToast("Please verify your login with OTP.", "success");
                }
            } else {
                showError(data.error || "Authentication failed.");
            }
        } catch(err) {
            showError("Network error. Server might be down.");
        }
    });

    otpForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const otp = authOtp.value.trim();
        
        try {
            const res = await fetch('/api/auth/verify-otp', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email: pendingEmail, otp})
            });
            const data = await res.json();
            
            if(res.ok) {
                localStorage.setItem('auth_token', data.token);
                localStorage.setItem('auth_email', pendingEmail);
                showToast("Verification successful!", "success");
                checkAuth();
            } else {
                showError(data.error || "Invalid OTP code.");
            }
        } catch(err) {
            showError("Network error.");
        }
    });

    btnBackToAuth.addEventListener('click', (e) => {
        e.preventDefault();
        authCardOtp.classList.add('hidden');
        authCardMain.classList.remove('hidden');
    });

    // Handle Real Google SSO response
    window.handleGoogleSsoResponse = async (response) => {
        try {
            const res = await fetch('/api/auth/google', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ token: response.credential })
            });
            const data = await res.json();
            
            if(res.ok) {
                localStorage.setItem('auth_token', data.token);
                localStorage.setItem('auth_email', data.email);
                showToast(`Successfully authenticated as ${data.email}`, "success");
                checkAuth();
            } else {
                showError(data.error || "Google SSO failed.");
            }
        } catch(err) {
            showError("Network error during Google SSO.");
        }
    };

    logoutBtn.addEventListener('click', () => {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_email');
        authEmail.value = '';
        document.getElementById('authPassword').value = '';
        authOtp.value = '';
        checkAuth();
        showToast("Logged out successfully.", "success");
    });

    // --- Core Extraction (Fast) ---

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();
        if(!url) return;

        showProcessing("Extracting transcript instantly...");

        try {
            const res = await fetch('/api/process', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url})
            });
            const data = await res.json();
            
            if(res.ok) {
                currentVideoId = data.id;
                // Switch to transcript tab by default
                document.querySelector('[data-tab="transcript"]').click();
                displayResults(data);
                fetchHistory();
            } else {
                showError(data.error || "Failed to process URL.");
                resetUI();
                fetchHistory();
            }
        } catch(err) {
            showError("Network error. Is the server running?");
            resetUI();
        }
    });

    // --- Generate Summary (Separate Step) ---
    
    generateSummaryBtn.addEventListener('click', async () => {
        if(!currentVideoId) return;
        
        generateSummaryBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
        generateSummaryBtn.disabled = true;

        try {
            const res = await fetch(`/api/summarize/${currentVideoId}`, { 
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    target_lang: targetLanguage.value,
                    gemini_key: localStorage.getItem('gemini_api_key') || ''
                })
            });
            const data = await res.json();
            
            if(res.ok) {
                renderSummary(data.summary);
            } else {
                showError("Failed to generate summary.");
            }
        } catch(err) {
            showError("Network error during summarization.");
        } finally {
            generateSummaryBtn.innerHTML = '<i class="fas fa-magic"></i> Generate Now';
            generateSummaryBtn.disabled = false;
        }
    });

    const displayResults = (data) => {
        hideProcessing();
        resultsCard.classList.remove('hidden');
        
        // Populate Transcript
        transcriptText.textContent = data.transcript;
        
        // Handle Summary Display
        if (data.summary && data.summary.length > 0) {
            renderSummary(data.summary);
        } else {
            summaryActionArea.classList.remove('hidden');
            summaryList.classList.add('hidden');
        }
    };

    const renderSummary = (bullets) => {
        summaryActionArea.classList.add('hidden');
        summaryList.classList.remove('hidden');
        summaryList.innerHTML = '';
        bullets.forEach(point => {
            const li = document.createElement('li');
            li.textContent = point;
            summaryList.appendChild(li);
        });
    };

    // --- UI Interactions ---

    // Tab Switching
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            
            btn.classList.add('active');
            document.getElementById(`${btn.dataset.tab}Tab`).classList.add('active');
        });
    });

    // Copy to Clipboard
    copyBtn.addEventListener('click', () => {
        const activeTab = document.querySelector('.tab-btn.active').dataset.tab;
        let textToCopy = '';
        if(activeTab === 'transcript') {
            textToCopy = transcriptText.textContent;
        } else {
            if(!summaryList.classList.contains('hidden')) {
                textToCopy = Array.from(summaryList.children).map(li => "• " + li.textContent).join('\n');
            } else {
                showToast("No summary generated yet.", "error");
                return;
            }
        }

        navigator.clipboard.writeText(textToCopy).then(() => {
            showToast("Copied to clipboard!", "success");
        }).catch(() => {
            showToast("Failed to copy.", "error");
        });
    });

    // New Extraction
    newTranscribeBtn.addEventListener('click', () => {
        resetUI();
        urlInput.value = '';
        urlInput.focus();
        document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
    });

    // History Fetching
    const fetchHistory = async () => {
        try {
            const res = await fetch('/api/history');
            const history = await res.json();
            renderHistory(history);
        } catch(err) {
            console.error(err);
        }
    };

    const renderHistory = (history) => {
        const activeId = currentVideoId;
        historyList.innerHTML = '';
        
        if(history.length === 0) {
            historyList.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 20px; font-size: 0.9rem;">No history yet</div>';
            return;
        }

        history.forEach(item => {
            const div = document.createElement('div');
            const isError = item.is_error;
            div.className = `history-item ${activeId === item.id ? 'active' : ''} ${isError ? 'error-item' : ''}`;
            
            const icon = isError ? "fa-exclamation-circle" : "fa-file-alt";
            
            div.innerHTML = `
                <i class="fas ${icon}"></i>
                <span title="${item.title || item.id}">${item.title || item.id}</span>
                <button class="btn-delete" title="Delete"><i class="fas fa-trash"></i></button>
            `;
            
            // Delete Action
            const deleteBtn = div.querySelector('.btn-delete');
            deleteBtn.addEventListener('click', async (e) => {
                e.stopPropagation(); // Prevent loading the transcript
                if(confirm("Are you sure you want to delete this transcript?")) {
                    try {
                        const res = await fetch(`/api/history/${item.id}`, { method: 'DELETE' });
                        if(res.ok) {
                            showToast("Deleted successfully", "success");
                            if(currentVideoId === item.id) {
                                resetUI();
                            }
                            fetchHistory();
                        } else {
                            showError("Failed to delete.");
                        }
                    } catch(err) {
                        showError("Error deleting item.");
                    }
                }
            });
            
            div.addEventListener('click', async () => {
                if(isError) {
                    showError("This video failed previously. Cannot load transcript.");
                    return;
                }
                
                document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
                div.classList.add('active');
                
                currentVideoId = item.id;
                showProcessing("Loading previous transcript...");
                
                try {
                    const res = await fetch(`/api/transcript/${item.id}`);
                    if(res.ok) {
                        const data = await res.json();
                        // Default to transcript view when loading history
                        document.querySelector('[data-tab="transcript"]').click();
                        displayResults(data);
                    } else {
                        showError("Transcript data corrupted or missing.");
                        resetUI();
                    }
                } catch(err) {
                    showError("Error loading transcript.");
                    resetUI();
                }
            });
            
            historyList.appendChild(div);
        });
    };

    // --- Translation Functionality ---
    btnTranslate.addEventListener('click', async () => {
        if(!currentVideoId) return;
        const lang = targetLanguage.value;
        const originalText = btnTranslate.innerHTML;
        btnTranslate.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Translating...';
        btnTranslate.disabled = true;

        try {
            const res = await fetch(`/api/translate/${currentVideoId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({target_lang: lang})
            });
            const data = await res.json();
            if(res.ok) {
                transcriptText.textContent = data.translated_text;
                showToast("Translated successfully!", "success");
            } else {
                showError("Translation failed: " + data.error);
            }
        } catch(err) {
            showError("Network error during translation.");
        } finally {
            btnTranslate.innerHTML = originalText;
            btnTranslate.disabled = false;
        }
    });

    // --- Helpers ---

    const showProcessing = (text) => {
        processingText.textContent = text;
        heroSection.classList.add('hidden');
        resultsCard.classList.add('hidden');
        processingState.classList.remove('hidden');
    };

    const hideProcessing = () => {
        processingState.classList.add('hidden');
    };

    const resetUI = () => {
        processingState.classList.add('hidden');
        resultsCard.classList.add('hidden');
        heroSection.classList.remove('hidden');
        currentVideoId = null;
    };

    // Beautiful Toasts
    const toastContainer = document.getElementById('toastContainer');
    const showToast = (message, type = 'error') => {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        const icon = type === 'error' ? 'fa-exclamation-circle' : 'fa-check-circle';
        
        toast.innerHTML = `
            <i class="fas ${icon}"></i>
            <span>${message}</span>
        `;
        
        toastContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'slideInRight 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    };

    const showError = (msg) => showToast(msg, 'error');

    // Theme Toggle
    themeToggle.addEventListener('click', () => {
        document.body.classList.toggle('light-theme');
        document.body.classList.toggle('dark-theme');
        const icon = themeToggle.querySelector('i');
        if(document.body.classList.contains('light-theme')) {
            icon.classList.remove('fa-sun');
            icon.classList.add('fa-moon');
        } else {
            icon.classList.remove('fa-moon');
            icon.classList.add('fa-sun');
        }
    });

    // Sidebar Toggle
    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
    });
    sidebarCloseBtn.addEventListener('click', () => {
        sidebar.classList.add('collapsed');
    });

    // Init App
    checkAuth();
});
