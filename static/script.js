document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const chatContainer = document.getElementById('chat-container');
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const micButton = document.getElementById('mic-button');
    const ttsToggleButton = document.getElementById('tts-toggle');
    const voiceModal = document.getElementById('voice-modal');
    const voiceModalStatus = document.getElementById('voice-modal-status');
    const closeModalBtn = document.getElementById('close-modal-btn');

    // --- State ---
    let isTtsEnabled = false;

    // --- WebSocket Connection ---
    const socket = new WebSocket(`ws://${window.location.host}/ws`);
    socket.onopen = () => console.log('WebSocket connection established.');
    socket.onerror = (error) => console.error('WebSocket Error:', error);

    // --- Web Speech API Setup ---
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition;
    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.lang = 'en-US';
        recognition.interimResults = false;
        recognition.onstart = () => { voiceModal.classList.remove('hidden'); voiceModalStatus.textContent = 'Listening...'; };
        recognition.onresult = (event) => { userInput.value = event.results[0][0].transcript; voiceModalStatus.textContent = 'Processing...'; chatForm.requestSubmit(); };
        recognition.onerror = (event) => { voiceModalStatus.textContent = `Error: ${event.error}`; };
        recognition.onend = () => { voiceModal.classList.add('hidden'); };
    } else {
        micButton.style.display = 'none';
    }

    // --- Event Listeners ---
    userInput.addEventListener('input', () => { userInput.style.height = 'auto'; userInput.style.height = `${userInput.scrollHeight}px`; });
    userInput.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); chatForm.requestSubmit(); } });
    micButton.addEventListener('click', () => recognition?.start());
    closeModalBtn.addEventListener('click', () => recognition?.stop());
    ttsToggleButton.addEventListener('click', () => { isTtsEnabled = !isTtsEnabled; ttsToggleButton.classList.toggle('active', isTtsEnabled); speak(isTtsEnabled ? "Voice feedback enabled" : "Voice feedback disabled"); });

    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const userPrompt = userInput.value.trim();
        if (!userPrompt) return;
        const commandId = `cmd-${Date.now()}`;
        
        createUserMessage(userPrompt);
        createJarvixResponseContainer(commandId);
        socket.send(JSON.stringify({ id: commandId, prompt: userPrompt }));
        userInput.value = '';
        userInput.style.height = 'auto';
    });
    
    chatContainer.addEventListener('click', function(event) {
        const copyBtn = event.target.closest('.copy-btn');
        if (copyBtn) {
            const pre = copyBtn.closest('pre');
            const code = pre.querySelector('code').innerText;
            navigator.clipboard.writeText(code).then(() => {
                copyBtn.textContent = 'Copied!';
                setTimeout(() => { copyBtn.textContent = 'Copy'; }, 2000);
            });
        }
    });

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        const commandElement = document.getElementById(data.id);
        if (!commandElement) return;

        const logContainer = commandElement.querySelector('.jarvix-log');
        const statusElement = commandElement.querySelector('.status');
        
        switch (data.type) {
            case 'stream': {
                let responseDiv = logContainer.querySelector('.gemini-response');
                if (!responseDiv) {
                     responseDiv = document.createElement('div');
                     responseDiv.className = 'gemini-response';
                     logContainer.appendChild(responseDiv);
                }
                // The server-side fix now ensures this runs before end_processing.
                responseDiv.innerHTML += formatMessage(data.message, true);
                break;
            }
            case 'log': {
                 const logEntry = document.createElement('div');
                 logEntry.innerHTML = formatMessage(data.message);
                 logContainer.appendChild(logEntry);
                 break;
            }
            case 'start_processing':
                 updateStatus(statusElement, 'processing', '🔄', 'Processing');
                 break;
            case 'end_processing': {
                const responseDiv = logContainer.querySelector('.gemini-response');
                if (responseDiv) {
                     responseDiv.innerHTML = formatMessage(responseDiv.innerHTML);
                }
                logContainer.querySelectorAll('pre:not(:has(.copy-btn))').forEach(pre => {
                     const button = document.createElement('button');
                     button.className = 'copy-btn';
                     button.textContent = 'Copy';
                     pre.appendChild(button);
                });

                // <<< FINAL STATUS CHECK: Rely purely on presence of success/error symbols
                const hasFailed = logContainer.innerHTML.includes('❌');
                const isSuccess = !hasFailed;
                
                const statusText = isSuccess ? 'Completed' : 'Failed';
                const statusIcon = isSuccess ? '✅' : '❌';
                updateStatus(statusElement, 'done', statusIcon, statusText);
                
                const summary = findSummary(logContainer.innerHTML);
                speak(summary || (isSuccess ? "Task completed" : "An error occurred"));

                // We no longer need to delete state, as we removed the state tracking object.
                break;
            }
        }
        chatContainer.scrollTop = chatContainer.scrollHeight;
    };

    // --- Helper Functions ---
    function speak(text) { if (!isTtsEnabled || !text) return; window.speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(text); utterance.lang = 'en-US'; window.speechSynthesis.speak(utterance); }
    function findSummary(htmlContent) { const match = htmlContent.match(/👍 \*\*Success:\*\* (.*?)(<\/strong>|<\/div>)/); return match ? match[1].trim().replace(/<[^>]*>?/gm, '') : null; }
    function init() { if (chatContainer.children.length === 0) { displayWelcomeMessage(); } }
    function displayWelcomeMessage() { 
        const w = `<div class="message jarvix-message"><div class="avatar">J</div><div class="text"><div style="font-size: 1.2rem; font-weight: 700; margin-bottom: 1rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">👋 Hello! I'm Jarvix Final</div><div style="opacity: 0.95; line-height: 1.9; font-size: 0.95rem;"><p style="margin-bottom: 1rem;">I'm your <strong>Cognitive Operating System</strong> — an intelligent AI coordinator that serves as your personal digital command center. Unlike traditional AI assistants, I operate in a <strong>hybrid mode</strong>, seamlessly working with both your local computer files and online resources.</p><div style="background: rgba(102, 126, 234, 0.1); border-left: 3px solid #667eea; padding: 1rem; border-radius: 8px; margin: 1rem 0;"><strong style="color: #667eea; display: block; margin-bottom: 0.5rem;">🎯 What Makes Me Unique:</strong><ul style="margin-left: 1.5rem; margin-top: 0.5rem; margin-bottom: 0;"><li style="margin-bottom: 0.5rem;"><strong>Hybrid Operation:</strong> I work directly with your computer's files, folders, and online resources simultaneously</li><li style="margin-bottom: 0.5rem;"><strong>Co-Creative Strategy:</strong> I help you plan and strategize, then execute with your approval</li><li style="margin-bottom: 0.5rem;"><strong>Project-Based Memory:</strong> Each project has its own isolated, permanent memory</li><li style="margin-bottom: 0;"><strong>Intuitive Interface:</strong> Designed for non-technical users, combining chat with visual project management</li></ul></div><div style="margin-top: 1.25rem;"><strong style="color: #667eea; display: block; margin-bottom: 0.75rem;">✨ What I Can Do:</strong><div style="display: grid; gap: 0.5rem;"><div>📊 <strong>Data Analysis:</strong> Analyze CSV/Excel files and generate comprehensive reports with visualizations</div><div>💬 <strong>Intelligent Conversations:</strong> Answer questions and provide strategic insights</div><div>📁 <strong>File Management:</strong> Work with files in your Downloads, Desktop, and other directories</div><div>🔗 <strong>Online Integration:</strong> Search the web, gather information, and combine it with your local data</div><div>📈 <strong>Report Generation:</strong> Create presentations, reports, and documents automatically</div></div></div><div style="margin-top: 1.5rem; padding: 1rem; background: rgba(118, 75, 162, 0.1); border-radius: 8px; border: 1px solid rgba(118, 75, 162, 0.2);"><strong style="color: #764ba2;">💡 Example Command:</strong><p style="margin-top: 0.5rem; margin-bottom: 0; font-style: italic; font-size: 0.9rem;">"Analyze my 'Sales_Q3.csv' file from Downloads, create visualizations, search for regional economic news online, and generate a PowerPoint presentation saved to my Desktop."</p></div><p style="margin-top: 1.25rem; margin-bottom: 0; text-align: center; font-weight: 600; color: #667eea;">Ready to transform your workflow? Try asking me to analyze a file or help with any task!</p></div></div></div>`; 
        chatContainer.innerHTML = w; 
    }
    function createUserMessage(text) { const m = document.createElement('div'); m.className = 'message user-message'; const escapedText = text.replace(/</g, "&lt;").replace(/>/g, "&gt;"); m.innerHTML = `<div class="text">${escapedText}</div><div class="avatar">U</div>`; chatContainer.appendChild(m); }
    function createJarvixResponseContainer(id) { const m = document.createElement('div'); m.className = 'message jarvix-message'; m.id = id; m.innerHTML = `<div class="avatar">J</div><div class="text"><div class="status pending"><span class="status-icon">🕒</span><span class="status-text">Queued</span></div><div class="jarvix-log"></div></div>`; chatContainer.appendChild(m); }
    function updateStatus(el, cl, ic, tx) { el.className = `status ${cl}`; el.innerHTML = `<span class="status-icon">${ic}</span> <span class="status-text">${tx}</span>`; }
    function formatMessage(text, isStream = false) { let formatted = isStream ? text : text.replace(/<br>/g, '\n'); formatted = formatted.replace(/</g, "&lt;").replace(/>/g, "&gt;"); if (!isStream) { formatted = formatted.replace(/&lt;pre&gt;&lt;code&gt;([\s\S]*?)&lt;\/code&gt;&lt;\/pre&gt;/g, (match, code) => `<pre><code>${code.trim()}</code></pre>`); } formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>'); return isStream ? formatted.replace(/\n/g, '<br>') : formatted; }
    
    init();
});