// ===========================
// Application State
// ===========================
const state = {
    apiUrl: window.location.origin,
    selectedDomain: 'retail_clothing',
    conversationHistory: [],
    currentResults: null,
    isLoading: false,
    isSentinelMode: true,
    sentinelScans: 0,
    sentinelDetections: [],
    conversationId: generateId()
};

// ===========================
// Utility Functions
// ===========================
function generateId() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

function getCurrentTime() {
    return new Date().toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ===========================
// DOM Elements
// ===========================
const elements = {
    messagesContainer: document.getElementById('messages'),
    queryInput: document.getElementById('query-input'),
    sendBtn: document.getElementById('send-btn'),
    clearChatBtn: document.getElementById('clear-chat'),
    apiUrlInput: document.getElementById('api-url'),
    connectionStatus: document.getElementById('connection-status'),
    resultsContent: document.getElementById('results-content'),
    toggleViewBtn: document.getElementById('toggle-view'),
    exportBtn: document.getElementById('export-btn'),
    domainBtns: document.querySelectorAll('.domain-btn'),
    exampleItems: document.querySelectorAll('.example-item'),
    sentinelBtn: document.getElementById('sentinel-btn'),
    sentinelDashboard: document.getElementById('sentinel-dashboard'),
    chatContainer: document.querySelector('.chat-container'),
    resultsPanel: document.getElementById('results-panel'),
    sentinelFeed: document.getElementById('sentinel-feed'),
    scanCount: document.getElementById('scan-count'),
    criticalAlertCount: document.getElementById('critical-alert-count'),
    detectionCount: document.getElementById('detection-count'),
    sentinelGlobalLoading: document.getElementById('sentinel-global-loading'),
    feeds: {
        security: document.getElementById('feed-security'),
        compliance: document.getElementById('feed-compliance'),
        operations: document.getElementById('feed-operations')
    }
};

// ===========================
// API Functions
// ===========================
async function checkApiConnection() {
    try {
        const response = await fetch(`${state.apiUrl}/health`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });

        if (response.ok) {
            updateConnectionStatus(true);
            return true;
        }
        throw new Error('API not healthy');
    } catch (error) {
        console.error('API connection failed:', error);
        updateConnectionStatus(false);
        return false;
    }
}

async function sendQuery(query) {
    try {
        const response = await fetch(`${state.apiUrl}/api/v1/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                domain: state.selectedDomain,
                conversation_id: state.conversationId,
                conversation_history: state.conversationHistory
            })
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('Query failed:', error);
        throw error;
    }
}

// ===========================
// UI Update Functions
// ===========================
function updateConnectionStatus(connected) {
    const statusIndicator = elements.connectionStatus.parentElement;
    if (connected) {
        statusIndicator.classList.add('connected');
        elements.connectionStatus.textContent = 'Connected';
    } else {
        statusIndicator.classList.remove('connected');
        elements.connectionStatus.textContent = 'Disconnected';
    }
}

function addMessage(content, type = 'user', options = {}) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    // Render as Markdown if marked library is available, otherwise fallback to escaped text
    if (typeof marked !== 'undefined') {
        contentDiv.innerHTML = marked.parse(content);
    } else {
        contentDiv.textContent = content;
    }

    const timestampDiv = document.createElement('div');
    timestampDiv.className = 'message-timestamp';
    timestampDiv.textContent = getCurrentTime();

    messageDiv.appendChild(contentDiv);
    messageDiv.appendChild(timestampDiv);

    // Add SQL block if present
    if (options.sql) {
        const sqlBlock = createSqlBlock(options.sql);
        messageDiv.appendChild(sqlBlock);
    }

    // Remove welcome message if exists
    const welcomeMsg = elements.messagesContainer.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    elements.messagesContainer.appendChild(messageDiv);

    // Scroll to bottom
    elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;

    return messageDiv;
}

function createSqlBlock(sql) {
    const sqlBlock = document.createElement('div');
    sqlBlock.className = 'sql-block';

    sqlBlock.innerHTML = `
        <div class="sql-header">
            <span class="sql-label">Generated SQL</span>
            <button class="copy-btn" onclick="copySqlToClipboard(this)">Copy</button>
        </div>
        <pre class="sql-code">${escapeHtml(sql)}</pre>
    `;

    return sqlBlock;
}

function showLoading() {
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'loading-indicator';
    loadingDiv.id = 'loading-indicator';

    loadingDiv.innerHTML = `
        <span>Thinking</span>
        <div class="loading-dots">
            <div class="loading-dot"></div>
            <div class="loading-dot"></div>
            <div class="loading-dot"></div>
        </div>
    `;

    elements.messagesContainer.appendChild(loadingDiv);
    elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;
}

function hideLoading() {
    const loadingDiv = document.getElementById('loading-indicator');
    if (loadingDiv) {
        loadingDiv.remove();
    }
}

function displayResults(response) {
    const results = response.results;
    const sql = response.sql;
    const visConfig = response.visualization_config;
    const insight = response.insight;
    const recommendation = response.recommendation;

    if (!results || results.length === 0) {
        elements.resultsContent.innerHTML = `
            <div class="empty-state">
                <h3>No Data Found</h3>
                <p>The query returned no results</p>
            </div>
        `;
        return;
    }

    state.currentResults = results;
    state.currentVisConfig = visConfig;
    state.currentInsight = insight;
    state.currentRecommendation = recommendation;

    // Clear previous content
    elements.resultsContent.innerHTML = '';

    // Create Insights Section
    const insightsSection = renderInsights(insight, recommendation);
    elements.resultsContent.appendChild(insightsSection);

    // Create Visualization Toolbar
    const toolbar = createVizToolbar(visConfig);
    elements.resultsContent.appendChild(toolbar);

    // Create container for visualization (chart or table)
    const vizContainer = document.createElement('div');
    vizContainer.id = 'viz-container';
    elements.resultsContent.appendChild(vizContainer);

    // Default to recommended visualization type if available, otherwise 'table'
    const defaultType = visConfig?.chart_type || 'table';
    renderVisualization(defaultType);
}

function renderInsights(insight, recommendation) {
    const container = document.createElement('div');
    container.className = 'insights-box';

    let insightHtml = '';
    if (insight) {
        const insightContent = Array.isArray(insight) ? insight.join(' ') : insight;
        insightHtml = `
            <div class="insight-item">
                <div class="insight-label">💡 AI Insight</div>
                <div class="insight-text">${marked.parse(insightContent)}</div>
            </div>
        `;
    }

    let recHtml = '';
    if (recommendation) {
        const recContent = Array.isArray(recommendation) ? recommendation.map(r => `<li>${r}</li>`).join('') : `<li>${recommendation}</li>`;
        recHtml = `
            <div class="rec-item">
                <div class="rec-label">⚖️ Recommended Action</div>
                <div class="rec-list">
                    <ul>${Array.isArray(recommendation) ? recContent : marked.parse(recommendation)}</ul>
                </div>
            </div>
        `;
    }

    container.innerHTML = insightHtml + recHtml;
    return container;
}

function createVizToolbar(visConfig) {
    const toolbar = document.createElement('div');
    toolbar.className = 'viz-toolbar';

    const label = document.createElement('span');
    label.className = 'viz-label';
    label.textContent = 'View As:';
    toolbar.appendChild(label);

    const recommendedType = visConfig?.chart_type || 'table';

    // Define available types
    const types = [
        { id: 'table', icon: '📋', label: 'Table' },
        { id: 'bar', icon: '📊', label: 'Bar' },
        { id: 'line', icon: '📈', label: 'Line' },
        { id: 'pie', icon: '🥧', label: 'Pie' }
    ];

    types.forEach(type => {
        const btn = document.createElement('button');
        btn.className = 'viz-btn';
        btn.dataset.type = type.id;

        let labelHtml = `<span class="viz-icon">${type.icon}</span> ${type.label}`;

        // Add recommendation badge if matches
        if (recommendedType === type.id && type.id !== 'table') {
            btn.classList.add('recommended');
            labelHtml += ` <span class="viz-badge">Recommended</span>`;
        }

        btn.innerHTML = labelHtml;

        btn.onclick = () => {
            // Update active state
            toolbar.querySelectorAll('.viz-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderVisualization(type.id);
        };

        // Set initial active state matching recommended or table
        if (type.id === recommendedType) {
            btn.classList.add('active');
        }

        toolbar.appendChild(btn);
    });

    return toolbar;
}

function renderVisualization(type) {
    const container = document.getElementById('viz-container');
    container.innerHTML = '';

    if (type === 'table') {
        const table = createDataTable(state.currentResults);
        container.appendChild(table);
    } else {
        // Create config override for the selected type
        let config = state.currentVisConfig;

        // If switching to a type different from recommendation, we need to adapt
        if (!config || config.chart_type !== type) {
            // Heuristic adaptation
            const columns = Object.keys(state.currentResults[0]);
            const numericColumns = columns.filter(col => {
                return state.currentResults.every(row => !isNaN(parseFloat(row[col])));
            });
            const labelColumn = columns.find(col => !numericColumns.includes(col)) || columns[0];

            config = {
                chart_type: type,
                x_axis_key: config?.x_axis_key || labelColumn,
                y_axis_key: config?.y_axis_key || numericColumns[0],
                title: config?.title || 'Data Visualization'
            };
        }

        const chart = createChart(state.currentResults, config);
        if (chart) {
            container.appendChild(chart);
        } else {
            container.innerHTML = '<div class="empty-state"><p>Cannot generate this chart with current data</p></div>';
        }
    }
}

function createDataTable(data) {
    const container = document.createElement('div');
    container.className = 'data-table-container';

    const table = document.createElement('table');
    table.className = 'data-table';

    // Create header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');

    const columns = Object.keys(data[0]);
    columns.forEach(col => {
        const th = document.createElement('th');
        th.textContent = col;
        headerRow.appendChild(th);
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);

    // Create body
    const tbody = document.createElement('tbody');
    data.forEach(row => {
        const tr = document.createElement('tr');
        columns.forEach(col => {
            const td = document.createElement('td');
            td.textContent = row[col] ?? 'N/A';
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    container.appendChild(table);

    return container;
}

function createChart(data, config) {
    if (data.length === 0) return null;

    // If explicit config says "table", don't show chart
    if (config && config.chart_type === 'table') return null;

    let chartType, xKey, yKeys, title;

    if (config) {
        // Use intelligent configuration from backend
        chartType = config.chart_type;
        xKey = config.x_axis_key;

        // Handle Y keys (could be string or array)
        if (Array.isArray(config.y_axis_key)) {
            yKeys = config.y_axis_key;
        } else {
            yKeys = [config.y_axis_key];
        }

        title = config.title;

        // Verify keys exist in data
        if (!data[0].hasOwnProperty(xKey)) {
            console.warn(`Chart X-axis key '${xKey}' not found in data. Falling back.`);
            config = null; // Fallback to auto-detection
        }
    }

    // Fallback Auto-Detection (if no config or invalid config)
    if (!config) {
        const columns = Object.keys(data[0]);
        const numericColumns = columns.filter(col => {
            return data.every(row => !isNaN(parseFloat(row[col])));
        });

        const labelColumn = columns.find(col => !numericColumns.includes(col)) || columns[0];

        if (numericColumns.length === 0 || data.length > 50) {
            return null;
        }

        chartType = data.length <= 10 ? 'bar' : 'line';
        xKey = labelColumn;
        yKeys = numericColumns.slice(0, 3); // Take top 3 numeric cols
        title = 'Data Visualization';
    }

    const container = document.createElement('div');
    container.className = 'chart-container';

    const titleDiv = document.createElement('div');
    titleDiv.className = 'chart-title';
    titleDiv.textContent = title || 'Data Visualization';
    container.appendChild(titleDiv);

    const canvas = document.createElement('canvas');
    canvas.className = 'chart-canvas';
    container.appendChild(canvas);

    // Prepare chart data
    const labels = data.map(row => row[xKey]);

    const datasets = yKeys.map((key, index) => {
        const colors = [
            { bg: 'rgba(0, 229, 255, 0.5)', border: 'rgb(0, 229, 255)' },
            { bg: 'rgba(124, 77, 255, 0.5)', border: 'rgb(124, 77, 255)' },
            { bg: 'rgba(0, 230, 118, 0.5)', border: 'rgb(0, 230, 118)' },
            { bg: 'rgba(255, 171, 0, 0.5)', border: 'rgb(255, 171, 0)' },
            { bg: 'rgba(255, 23, 68, 0.5)', border: 'rgb(255, 23, 68)' }
        ];

        // Cycle colors if more datasets than colors
        const color = colors[index % colors.length];

        return {
            label: key,
            data: data.map(row => parseFloat(row[key]) || 0),
            backgroundColor: color.bg,
            borderColor: color.border,
            borderWidth: 2,
            tension: 0.4,
            fill: chartType === 'area' // Fill if it's an area chart
        };
    });

    // Map backend chart types to Chart.js types
    const chartJsMap = {
        'bar': 'bar',
        'line': 'line',
        'pie': 'pie',
        'doughnut': 'doughnut',
        'scatter': 'scatter',
        'area': 'line' // Area is line with fill
    };

    const finalType = chartJsMap[chartType] || 'bar';

    // Create chart
    new Chart(canvas, {
        type: finalType,
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: yKeys.length > 0,
                    position: 'top',
                    labels: {
                        color: '#e0f7fa',
                        font: { family: 'Inter', size: 12 }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(3, 7, 18, 0.95)',
                    titleColor: '#e0f7fa',
                    bodyColor: '#80cbc4',
                    borderColor: 'rgba(0, 229, 255, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(0, 229, 255, 0.06)' },
                    ticks: {
                        color: '#80cbc4',
                        font: { family: 'Inter', size: 11 }
                    },
                    display: !['pie', 'doughnut'].includes(finalType)
                },
                y: {
                    grid: { color: 'rgba(0, 229, 255, 0.06)' },
                    ticks: {
                        color: '#80cbc4',
                        font: { family: 'Inter', size: 11 }
                    },
                    display: !['pie', 'doughnut'].includes(finalType)
                }
            }
        }
    });

    return container;
}

function showError(message) {
    addMessage(`❌ Error: ${message}`, 'assistant');
}

// ===========================
// Event Handlers
// ===========================
async function sendQuery(query) {
    const response = await fetch(`${state.apiUrl}/api/v1/query`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            query: query,
            domain: state.selectedDomain || 'retail_clothing',
            conversation_id: state.conversationId,
            conversation_history: state.conversationHistory
        })
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = typeof errorData.detail === 'string' 
            ? errorData.detail 
            : (errorData.detail?.[0]?.msg || errorData.message || `API error: ${response.status}`);
        throw new Error(errorMsg);
    }

    return await response.json();
}

async function handleSendMessage() {
    const query = elements.queryInput.value.trim();

    if (!query || state.isLoading) return;

    // Add user message
    addMessage(query, 'user');

    // Update conversation history
    state.conversationHistory.push({
        role: 'user',
        content: query
    });

    // Clear input
    elements.queryInput.value = '';
    elements.queryInput.style.height = 'auto';

    // Set loading state
    state.isLoading = true;
    elements.sendBtn.disabled = true;
    showLoading();

    try {
        // Send query to API
        const response = await sendQuery(query);

        hideLoading();

        // Handle different response statuses
        if (response.status === 'needs_clarification') {
            addMessage(response.clarification_question, 'assistant');
            state.conversationHistory.push({
                role: 'assistant',
                content: response.clarification_question
            });
        } else if (response.status === 'success') {
            // Build rich AI response with insight + recommendation
            let aiReply = '';
            const rowCount = response.results?.length || 0;

            // Add insight
            if (response.insight) {
                const insightText = Array.isArray(response.insight) ? response.insight.join('\n\n') : response.insight;
                aiReply += `**📊 Analysis** *(${rowCount} records found)*\n\n${insightText}`;
            } else {
                aiReply += `✅ Query executed successfully — **${rowCount} records** returned.`;
            }

            // Add recommendation
            if (response.recommendation) {
                aiReply += '\n\n---\n\n';
                if (Array.isArray(response.recommendation)) {
                    aiReply += '**⚖️ Recommended Actions:**\n';
                    response.recommendation.forEach(r => { aiReply += `- ${r}\n`; });
                } else {
                    aiReply += `**⚖️ Recommended Action:** ${response.recommendation}`;
                }
            }

            addMessage(aiReply, 'assistant', { sql: response.sql });

            state.conversationHistory.push({
                role: 'assistant',
                content: aiReply
            });

            // Display results in results panel + auto-show it
            elements.resultsPanel.classList.remove('hidden');
            displayResults(response);
        } else if (response.status === 'failed') {
            showError(response.error || 'Query execution failed');
            if (response.sql) {
                const lastMessage = elements.messagesContainer.lastElementChild;
                const sqlBlock = createSqlBlock(response.sql);
                lastMessage.appendChild(sqlBlock);
            }
        } else {
            showError('Unexpected response from server');
        }
    } catch (error) {
        hideLoading();
        showError(error.message || 'Failed to connect to the API. Please make sure the server is running.');
    } finally {
        state.isLoading = false;
        elements.sendBtn.disabled = false;
    }
}

function handleClearChat() {
    state.conversationHistory = [];
    state.conversationId = generateId();
    state.currentResults = null;
    state.currentVisConfig = null;
    state.currentInsight = null;
    state.currentRecommendation = null;

    elements.messagesContainer.innerHTML = `
        <div class="welcome-message">
            <h2>👋 Welcome to DerivInsight</h2>
            <p>Ask me anything about your data in natural language. I'll convert it to SQL and show you the results!</p>
            <div class="welcome-features">
                <div class="feature">
                    <span class="feature-icon">🤖</span>
                    <span>AI-Powered Queries</span>
                </div>
                <div class="feature">
                    <span class="feature-icon">📊</span>
                    <span>Visual Analytics</span>
                </div>
                <div class="feature">
                    <span class="feature-icon">⚡</span>
                    <span>Real-time Results</span>
                </div>
            </div>
        </div>
    `;

    elements.resultsContent.innerHTML = `
        <div class="empty-state">
            <svg width="120" height="120" viewBox="0 0 120 120" fill="none">
                <circle cx="60" cy="60" r="50" stroke="url(#emptyGradient)" stroke-width="2" opacity="0.3"/>
                <path d="M60 40v40M40 60h40" stroke="url(#emptyGradient)" stroke-width="2" stroke-linecap="round"/>
                <defs>
                    <linearGradient id="emptyGradient" x1="0" y1="0" x2="120" y2="120">
                        <stop offset="0%" stop-color="#00e5ff"/>
                        <stop offset="100%" stop-color="#7c4dff"/>
                    </linearGradient>
                </defs>
            </svg>
            <h3>No Results Yet</h3>
            <p>Run a query to see data visualizations and tables here</p>
        </div>
    `;
}

function handleDomainChange(domain) {
    state.selectedDomain = domain;

    // Update sidebar UI buttons
    elements.domainBtns.forEach(btn => {
        if (btn.dataset.domain === domain) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // Update first-page domain cards
    document.querySelectorAll('.domain-card').forEach(card => {
        if (card.dataset.domain === domain) {
            card.classList.add('active');
        } else {
            card.classList.remove('active');
        }
    });
}

function handleExampleClick(query) {
    if (state.isSentinelMode) {
        toggleSentinelMode();
    }
    elements.queryInput.value = query;
    elements.queryInput.focus();

    // Auto-adjust textarea height
    elements.queryInput.style.height = 'auto';
    elements.queryInput.style.height = elements.queryInput.scrollHeight + 'px';
}

function handleExport(format = 'csv') {
    if (!state.currentResults || state.currentResults.length === 0) {
        alert('No data to export');
        return;
    }

    if (format === 'excel') {
        exportAsExcel();
    } else {
        exportAsCSV();
    }
}

function exportAsCSV() {
    const columns = Object.keys(state.currentResults[0]);
    const csv = [
        columns.join(','),
        ...state.currentResults.map(row =>
            columns.map(col => {
                const value = row[col] ?? '';
                const str = String(value);
                return (str.includes(',') || str.includes('"') || str.includes('\n'))
                    ? `"${str.replace(/"/g, '""')}"`
                    : str;
            }).join(',')
        )
    ].join('\n');

    downloadFile(csv, `query-results-${Date.now()}.csv`, 'text/csv;charset=utf-8;');
}

function exportAsExcel() {
    const columns = Object.keys(state.currentResults[0]);

    // Build XML Spreadsheet (Excel-compatible)
    let xml = '<?xml version="1.0" encoding="UTF-8"?>';
    xml += '<?mso-application progid="Excel.Sheet"?>';
    xml += '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"';
    xml += ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">';
    xml += '<Worksheet ss:Name="Results"><Table>';

    // Header row
    xml += '<Row>';
    columns.forEach(col => {
        xml += `<Cell><Data ss:Type="String">${escapeXml(col)}</Data></Cell>`;
    });
    xml += '</Row>';

    // Data rows
    state.currentResults.forEach(row => {
        xml += '<Row>';
        columns.forEach(col => {
            const val = row[col] ?? '';
            const isNum = !isNaN(parseFloat(val)) && isFinite(val);
            const type = isNum ? 'Number' : 'String';
            xml += `<Cell><Data ss:Type="${type}">${escapeXml(String(val))}</Data></Cell>`;
        });
        xml += '</Row>';
    });

    xml += '</Table></Worksheet></Workbook>';

    downloadFile(xml, `query-results-${Date.now()}.xls`, 'application/vnd.ms-excel');
}

function escapeXml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

function toggleExportDropdown() {
    const dropdown = document.getElementById('export-dropdown');
    if (dropdown) {
        dropdown.classList.toggle('hidden');
    }
}

// ===========================
// Sentinel Functions
// ===========================
async function toggleSentinelMode() {
    state.isSentinelMode = !state.isSentinelMode;

    if (state.isSentinelMode) {
        elements.sentinelBtn.classList.add('active');
        elements.chatContainer.classList.add('hidden');
        elements.resultsPanel.classList.add('hidden');
        elements.sentinelDashboard.classList.remove('hidden');
        elements.sentinelBtn.innerHTML = '<span class="icon">💬</span> QUERY CHAT';
        runSentinelScan();
    } else {
        elements.sentinelBtn.classList.remove('active');
        elements.chatContainer.classList.remove('hidden');
        elements.resultsPanel.classList.remove('hidden');
        elements.sentinelDashboard.classList.add('hidden');
        elements.sentinelBtn.innerHTML = '<span class="pulse-ring"></span><span class="icon">🛰️</span> SENTINEL MODE';
    }
}

async function runSentinelScan() {
    elements.sentinelGlobalLoading.classList.remove('hidden');
    Object.values(elements.feeds).forEach(f => f.innerHTML = '');

    try {
        const response = await fetch(`${state.apiUrl}/api/v1/sentinel/scan`);
        const data = await response.json();

        state.sentinelScans++;
        state.sentinelDetections = data.detections;

        renderSentinelDetections(data.detections);
        updateSentinelStats(data.detections);
    } catch (error) {
        console.error('Sentinel Scan Failed:', error);
    } finally {
        elements.sentinelGlobalLoading.classList.add('hidden');
    }
}

function renderSentinelDetections(detections) {
    // Group detections for 3 columns
    const columns = {
        security: detections.filter(d => d.domain === 'security' || d.domain === 'risk'),
        compliance: detections.filter(d => d.domain === 'compliance'),
        operations: detections.filter(d => d.domain === 'operations')
    };

    Object.keys(columns).forEach(colKey => {
        const container = elements.feeds[colKey];
        columns[colKey].forEach(det => {
            container.appendChild(createDetectionCard(det));
        });
    });
}

function createDetectionCard(det) {
    const card = document.createElement('div');
    card.className = `detection-card severity-${det.severity} mini`;

    // Create visualization if recommended
    let chartHtml = '';
    const hasData = det.results && det.results.length > 0;
    const hasViz = det.visualization_config && det.visualization_config.chart_type !== 'table';

    if (hasData && hasViz) {
        chartHtml = `<div class="mini-chart-container"><canvas id="chart-${det.mission_id}"></canvas></div>`;
    }

    card.innerHTML = `
        <div class="detection-meta">
            <span class="severity-pill ${det.severity}">${det.severity}</span>
            <span class="detection-time">LIVE</span>
        </div>
        <div class="detection-body">
            <h5>${det.mission_name}</h5>
            ${chartHtml}
            <div class="compact-insight">
                ${marked.parse(det.insight || '')}
            </div>
            ${det.recommendation ? `
                <div class="mini-rec">
                    <strong>Protocol:</strong> ${Array.isArray(det.recommendation) ? det.recommendation[0] : (typeof det.recommendation === 'string' ? det.recommendation.substring(0, 100) : '')}
                </div>
            ` : ''}
        </div>
    `;

    // Initialize chart if needed after element is in DOM
    if (hasData && hasViz) {
        setTimeout(() => {
            const canvas = document.getElementById(`chart-${det.mission_id}`);
            if (canvas) {
                createMiniChart(canvas, det.results, det.visualization_config);
            }
        }, 100);
    }

    return card;
}

function createMiniChart(canvas, data, config) {
    const ctx = canvas.getContext('2d');
    const chartType = config.chart_type === 'area' ? 'line' : (config.chart_type || 'bar');

    // Safety check for keys
    const xKey = config.x_axis_key;
    const yKey = Array.isArray(config.y_axis_key) ? config.y_axis_key[0] : config.y_axis_key;

    new Chart(ctx, {
        type: chartType,
        data: {
            labels: data.slice(0, 5).map(row => row[xKey] || 'N/A'),
            datasets: [{
                label: yKey,
                data: data.slice(0, 5).map(row => parseFloat(row[yKey]) || 0),
                backgroundColor: 'rgba(0, 229, 255, 0.3)',
                borderColor: '#00e5ff',
                borderWidth: 1,
                fill: config.chart_type === 'area'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: true } },
            scales: {
                x: { display: false },
                y: { display: false }
            }
        }
    });
}

function updateSentinelStats(detections) {
    elements.scanCount.textContent = state.sentinelScans;
    elements.detectionCount.textContent = detections.length;

    const criticalCount = detections.filter(d => d.severity === 'CRITICAL').length;
    elements.criticalAlertCount.textContent = criticalCount;
}

async function runDomainScan(domain) {
    const sectionId = domain === 'risk' ? 'security' : domain;
    const feedContainer = elements.feeds[sectionId];
    const section = document.getElementById(`section-${sectionId}`);
    const scanBtn = section?.querySelector('.section-scan-btn');

    if (!feedContainer) return;

    // Show loading state on button
    if (scanBtn) {
        scanBtn.disabled = true;
        scanBtn.innerHTML = '<span class="scan-spinner"></span> SCANNING...';
    }
    feedContainer.innerHTML = '<div class="section-loading"><div class="scanner-bar"></div><p>Scanning...</p></div>';

    try {
        const response = await fetch(`${state.apiUrl}/api/v1/sentinel/scan/${domain}`);
        const data = await response.json();

        state.sentinelScans++;

        // Render detections into the specific section
        feedContainer.innerHTML = '';
        const detections = data.detections || [];
        detections.forEach(det => {
            feedContainer.appendChild(createDetectionCard(det));
        });

        // Merge into global detections for stats
        state.sentinelDetections = [
            ...state.sentinelDetections.filter(d => {
                const dSection = d.domain === 'risk' ? 'security' : d.domain;
                return dSection !== sectionId;
            }),
            ...detections
        ];
        updateSentinelStats(state.sentinelDetections);
    } catch (error) {
        console.error(`Domain scan failed (${domain}):`, error);
        feedContainer.innerHTML = `<div class="scan-error">Scan failed: ${error.message}</div>`;
    } finally {
        if (scanBtn) {
            scanBtn.disabled = false;
            scanBtn.innerHTML = '⚡ SCAN';
        }
    }
}

// ===========================
// Global Functions (for inline handlers)
// ===========================
window.copySqlToClipboard = function (btn) {
    const sqlBlock = btn.closest('.sql-block');
    const sqlCode = sqlBlock.querySelector('.sql-code').textContent;

    navigator.clipboard.writeText(sqlCode).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => {
            btn.textContent = 'Copy';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
        alert('Failed to copy to clipboard');
    });
};

// ===========================
// Event Listeners
// ===========================
elements.sendBtn.addEventListener('click', handleSendMessage);

elements.queryInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage();
    }
});

// Auto-resize textarea
elements.queryInput.addEventListener('input', (e) => {
    e.target.style.height = 'auto';
    e.target.style.height = e.target.scrollHeight + 'px';
});

elements.clearChatBtn.addEventListener('click', handleClearChat);

elements.apiUrlInput.addEventListener('change', (e) => {
    state.apiUrl = e.target.value.trim();
    checkApiConnection();
});

elements.domainBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        handleDomainChange(btn.dataset.domain);
    });
});

elements.exampleItems.forEach(item => {
    item.addEventListener('click', () => {
        handleExampleClick(item.dataset.query);
    });
});

elements.exportBtn.addEventListener('click', () => toggleExportDropdown());
elements.sentinelBtn.addEventListener('click', toggleSentinelMode);
if (elements.toggleViewBtn) {
    elements.toggleViewBtn.addEventListener('click', () => {
        if (!state.currentResults || state.currentResults.length === 0) return;
        const vizContainer = document.getElementById('viz-container');
        if (!vizContainer) return;
        const isTable = vizContainer.querySelector('.data-table-container') !== null;
        const targetType = isTable ? (state.currentVisConfig?.chart_type || 'bar') : 'table';
        renderVisualization(targetType);

        // Sync button active state in viz toolbar
        const toolbar = elements.resultsContent.querySelector('.viz-toolbar');
        if (toolbar) {
            toolbar.querySelectorAll('.viz-btn').forEach(b => {
                if (b.dataset.type === targetType) {
                    b.classList.add('active');
                } else {
                    b.classList.remove('active');
                }
            });
        }
    });
}

// ===========================
// Initialization
// ===========================
async function initialize() {
    console.log('🚀 Initializing DerivInsight Frontend...');

    // Check API connection
    await checkApiConnection();

    // Set initial domain
    handleDomainChange('retail_clothing');

    // Focus input
    elements.queryInput.focus();

    if (state.isSentinelMode) {
        elements.sentinelBtn.innerHTML = '<span class="icon">💬</span> QUERY CHAT';
        runSentinelScan();
    }

    console.log('✅ Initialization complete');
}

// Start the app when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
} else {
    initialize();
}

// ===========================
// Tab & View Switching (Project 1 & Project 2 & Insights)
// ===========================
function switchToTab(tabName) {
    const chatContainer = document.querySelector('.chat-container');
    const sentinelDashboard = document.getElementById('sentinel-dashboard');
    const project2Dashboard = document.getElementById('project2-dashboard');
    const resultsPanel = document.getElementById('results-panel');
    const insightsDashboard = document.getElementById('insights-dashboard');

    const tabChat = document.getElementById('tab-chat');
    const tabSentinel = document.getElementById('tab-sentinel');
    const tabProject2 = document.getElementById('tab-project2');
    const tabInsights = document.getElementById('tab-insights');

    // Hide all main containers
    if (chatContainer) chatContainer.classList.add('hidden');
    if (sentinelDashboard) sentinelDashboard.classList.add('hidden');
    if (project2Dashboard) project2Dashboard.classList.add('hidden');
    if (resultsPanel) resultsPanel.classList.add('hidden');
    if (insightsDashboard) insightsDashboard.classList.add('hidden');

    // Reset active tab styles
    [tabChat, tabSentinel, tabProject2, tabInsights].forEach(t => { if (t) t.classList.remove('active'); });

    if (tabName === 'chat') {
        if (chatContainer) chatContainer.classList.remove('hidden');
        if (tabChat) tabChat.classList.add('active');
    } else if (tabName === 'sentinel') {
        if (sentinelDashboard) sentinelDashboard.classList.remove('hidden');
        if (tabSentinel) tabSentinel.classList.add('active');
    } else if (tabName === 'project2') {
        if (project2Dashboard) {
            project2Dashboard.classList.remove('hidden');
            project2Dashboard.style.display = 'block';
            const iframe = document.getElementById('project2-iframe');
            if (iframe && (!iframe.src || iframe.src === '' || iframe.src === 'about:blank')) {
                iframe.src = 'http://localhost:3000';
            }
            project2Dashboard.scrollIntoView({ behavior: 'smooth' });
        }
        if (tabProject2) tabProject2.classList.add('active');
    } else if (tabName === 'insights') {
        if (insightsDashboard) {
            insightsDashboard.classList.remove('hidden');
            insightsDashboard.style.display = 'block';
        }
        if (tabInsights) tabInsights.classList.add('active');
        // Auto-fetch insights on tab switch
        fetchAutoInsights();
    }
}
window.switchToTab = switchToTab;

// ===========================
// Auto Insights Dashboard Engine
// ===========================
let _autoInsightsData = [];

async function fetchAutoInsights() {
    const findingsContainer = document.getElementById('insights-findings');
    const lastUpdate = document.getElementById('last-insights-update');

    if (findingsContainer) {
        findingsContainer.innerHTML = `
            <div style="text-align: center; padding: 2rem; color: #667;">
                <div class="scanner-bar" style="margin-bottom: 1rem;"></div>
                <p>Fetching latest insights...</p>
            </div>`;
    }

    const host = window.location.hostname || 'localhost';
    const baseUrl = `${window.location.protocol}//${host}:8080`;

    try {
        const res = await fetch(`${baseUrl}/api/v1/insights/today?domain=${state.currentDomain || 'retail_clothing'}`);
        const data = await res.json();
        _autoInsightsData = data.insights || [];

        // Update proactive summary headline banner
        const headlineEl = document.getElementById('proactive-headline-text');
        if (headlineEl && data.summary_headline) {
            headlineEl.textContent = data.summary_headline;
        }

        const badgeEl = document.getElementById('urgent-badge');
        if (badgeEl && data.urgent_count !== undefined) {
            badgeEl.textContent = data.urgent_count > 0 ? `${data.urgent_count} URGENT` : 'NORMAL';
            badgeEl.style.backgroundColor = data.urgent_count > 0 ? '#e53e3e' : '#38a169';
        }

        updateRuleCounters(_autoInsightsData);
        renderInsightCards(_autoInsightsData, findingsContainer);

        if (lastUpdate) {
            const now = new Date();
            lastUpdate.textContent = now.toLocaleTimeString();
        }

        console.log(`📊 Auto Insights: ${_autoInsightsData.length} insights loaded (${data.summary_headline || 'no headline'})`);
    } catch (err) {
        console.error('Auto Insights fetch failed:', err);
        if (findingsContainer) {
            findingsContainer.innerHTML = `
                <div class="insights-empty-state">
                    <div class="empty-icon">⚠️</div>
                    <p style="color: #ff5252;">Failed to fetch insights: ${err.message}</p>
                    <p style="font-size: 0.8rem; margin-top: 0.5rem;">Ensure the backend is running on port 8080</p>
                </div>`;
        }
    }
}
window.fetchAutoInsights = fetchAutoInsights;

function updateRuleCounters(insights) {
    const stockoutCount = insights.filter(i => i.type === 'stockout' || i.insight_type === 'stockout' || i.type === 'stockout_risk').length;
    const criticalCount = insights.filter(i => (i.severity || '').toLowerCase() === 'critical' || (i.severity || '').toLowerCase() === 'high').length;
    const salesDropCount = insights.filter(i => i.type === 'sales_drop' || i.insight_type === 'sales_drop').length;
    const supplierCount = insights.filter(i => i.type === 'supplier_risk' || i.insight_type === 'supplier_risk').length;

    const total = insights.length || 1;

    const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    setEl('stockout-count', stockoutCount);
    setEl('stockout-percent', Math.round((stockoutCount / total) * 100) + '%');
    setEl('critical-count', criticalCount);
    setEl('critical-percent', Math.round((criticalCount / total) * 100) + '%');
    setEl('sales-drop-count', salesDropCount);
    setEl('sales-drop-percent', Math.round((salesDropCount / total) * 100) + '%');
    setEl('supplier-count', supplierCount);
    setEl('supplier-percent', Math.round((supplierCount / total) * 100) + '%');
}

function renderInsightCards(insights, container) {
    if (!container) return;

    if (!insights || insights.length === 0) {
        container.innerHTML = `
            <div class="insights-empty-state">
                <div class="empty-icon">✅</div>
                <p>No active insights detected today.</p>
                <p style="font-size: 0.8rem; margin-top: 0.5rem;">All inventory and sales metrics are within normal thresholds.</p>
            </div>`;
        return;
    }

    let html = '';
    insights.forEach((insight, idx) => {
        const sev = (insight.severity || 'medium').toLowerCase();
        const sevClass = `severity-${sev}`;
        const sevBadgeClass = `sev-${sev}`;
        const readClass = insight.is_read ? 'is-read' : '';
        const insightId = insight.insight_id || insight.id;
        const type = insight.type || insight.insight_type || '';
        const typeIcon = type.includes('stockout') ? '🛡️' :
                         type.includes('sales_drop') ? '📉' :
                         type.includes('supplier') ? '⚠️' :
                         type.includes('critical') ? '🔴' : '📊';

        const showPOButton = insight.suggested_reorder_qty > 0 || (insight.recommended_action && insight.recommended_action.includes('Reorder'));
        const pId = insight.product_id || insight.sku || '';
        const pName = (insight.product_name || insight.title || '').replace(/'/g, "\\'");
        const reorderQty = insight.suggested_reorder_qty || 15;

        const poButtonHtml = showPOButton ? `
            <button class="create-po-btn" id="po-btn-${insightId}" onclick="createDraftPOFromInsight('${insightId}', '${pId}', '${pName}', ${reorderQty})" style="background: linear-gradient(135deg, #00e5ff, #0072ff); color: #000; font-weight: 600; border: none; padding: 0.4rem 0.8rem; border-radius: 6px; cursor: pointer; font-size: 0.8rem; margin-left: 0.5rem; transition: all 0.2s ease;">
                📦 Create Draft PO
            </button>` : '';

        const recActionHtml = insight.recommended_action ? `
            <div class="finding-action-box" style="margin: 0.6rem 0 0.4rem 0; padding: 0.5rem 0.75rem; background: rgba(0, 229, 255, 0.08); border: 1px solid rgba(0, 229, 255, 0.25); border-radius: 6px; font-size: 0.85rem; color: #00e5ff; display: flex; align-items: center; gap: 0.5rem;">
                <span style="font-size: 1rem;">🎯</span>
                <div><strong>Recommended Action:</strong> ${insight.recommended_action}</div>
            </div>` : '';

        html += `
            <div class="insight-finding-card ${sevClass} ${readClass}" id="insight-card-${insightId}" style="animation-delay: ${idx * 0.08}s;">
                <div class="finding-header">
                    <span class="finding-title">${typeIcon} ${insight.title || 'Insight'}</span>
                    <span class="finding-severity ${sevBadgeClass}">${sev}</span>
                </div>
                <div class="finding-description">${insight.description || ''}</div>
                ${recActionHtml}
                <div class="finding-meta">
                    <span class="finding-product">${insight.product_name ? 'Product: ' + insight.product_name : (insight.product_id ? 'SKU: ' + insight.product_id : '')}</span>
                    <span class="finding-time">${insight.created_at || ''}</span>
                    <div style="display: flex; gap: 0.4rem; align-items: center;">
                        ${poButtonHtml}
                        <button class="mark-read-btn" onclick="markInsightRead('${insightId}')">✓ Acknowledge</button>
                    </div>
                </div>
            </div>`;
    });

    container.innerHTML = html;
}

async function createDraftPOFromInsight(insightId, productId, productName, quantity) {
    const btn = document.getElementById(`po-btn-${insightId}`);
    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Creating PO...';
    }

    const host = window.location.hostname || 'localhost';
    const baseUrl = `${window.location.protocol}//${host}:8080`;

    try {
        const response = await fetch(`${baseUrl}/api/v1/purchase-orders/draft`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                product_id: productId || 'SKU-UNKNOWN',
                product_name: productName || 'Requested Item',
                quantity: parseInt(quantity) || 15,
                notes: `Created from Auto Insight (${insightId})`
            })
        });

        const data = await response.json();

        if (response.ok && data.status === 'success') {
            if (btn) {
                btn.style.background = '#38a169';
                btn.style.color = '#fff';
                btn.textContent = `✓ Created (${data.po_number})`;
            }
            alert(`✅ Draft Purchase Order ${data.po_number} created successfully!\n\nProduct: ${productName}\nQuantity: ${quantity} units`);
        } else {
            throw new Error(data.detail || 'Failed to create Draft PO');
        }
    } catch (err) {
        console.error('Create Draft PO error:', err);
        if (btn) {
            btn.disabled = false;
            btn.textContent = '📦 Create Draft PO';
        }
        alert(`⚠️ Could not create Draft PO: ${err.message}`);
    }
}
window.createDraftPOFromInsight = createDraftPOFromInsight;

async function markInsightRead(insightId) {
    const host = window.location.hostname || 'localhost';
    const baseUrl = `${window.location.protocol}//${host}:8080`;

    try {
        await fetch(`${baseUrl}/api/v1/insights/read/${insightId}`, { method: 'PATCH' });
        const card = document.getElementById(`insight-card-${insightId}`);
        if (card) {
            card.classList.add('is-read');
        }
        console.log(`📊 Insight ${insightId} marked as read`);
    } catch (err) {
        console.error(`Failed to mark insight ${insightId} as read:`, err);
    }
}
window.markInsightRead = markInsightRead;

async function acknowledgeAllInsights() {
    const host = window.location.hostname || 'localhost';
    const baseUrl = `${window.location.protocol}//${host}:8080`;

    for (const insight of _autoInsightsData) {
        const id = insight.insight_id || insight.id;
        if (!insight.is_read) {
            try {
                await fetch(`${baseUrl}/api/v1/insights/read/${id}`, { method: 'PATCH' });
            } catch (e) { /* continue */ }
        }
    }
    // Refresh
    fetchAutoInsights();
}
window.acknowledgeAllInsights = acknowledgeAllInsights;

// Wire up Refresh and Acknowledge All buttons
document.addEventListener('DOMContentLoaded', () => {
    const refreshBtn = document.getElementById('refresh-insights-btn');
    if (refreshBtn) refreshBtn.addEventListener('click', fetchAutoInsights);

    const ackAllBtn = document.getElementById('acknowledge-all-btn');
    if (ackAllBtn) ackAllBtn.addEventListener('click', acknowledgeAllInsights);
});

// Close export dropdown when clicking outside
document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('export-dropdown');
    const exportBtn = elements.exportBtn;
    if (dropdown && !dropdown.contains(e.target) && exportBtn && !exportBtn.contains(e.target)) {
        dropdown.classList.add('hidden');
    }

    const domainCard = e.target.closest('.domain-card');
    if (domainCard && domainCard.dataset.domain) {
        handleDomainChange(domainCard.dataset.domain);
    }

    if (e.target.closest('#project2-btn')) {
        switchToTab('project2');
    }
});

// ===========================
// Project 2 (Next.js Hub) Interactive Controllers
// ===========================
function toggleProject2Mode() {
    const nativeView = document.getElementById('project2-native-view');
    const iframeView = document.getElementById('project2-iframe-view');
    const toggleBtn = document.getElementById('p2-mode-toggle');

    if (!nativeView || !iframeView) return;

    if (nativeView.style.display === 'none') {
        nativeView.style.display = 'block';
        iframeView.style.display = 'none';
        if (toggleBtn) toggleBtn.innerHTML = '🖥️ Switch View Mode';
    } else {
        nativeView.style.display = 'none';
        iframeView.style.display = 'block';
        const iframe = document.getElementById('project2-iframe');
        if (iframe && (!iframe.src || iframe.src === '' || iframe.src === 'about:blank')) {
            iframe.src = 'http://localhost:3000';
        }
        if (toggleBtn) toggleBtn.innerHTML = '🎛️ Switch View Mode';
    }
}
window.toggleProject2Mode = toggleProject2Mode;

async function fetchProject2Ontology() {
    const skuInput = document.getElementById('p2-sku-input');
    const inspectBtn = document.getElementById('p2-inspect-btn');
    const pricingContent = document.getElementById('p2-pricing-content');
    const supplyContent = document.getElementById('p2-supply-content');
    const carbonContent = document.getElementById('p2-carbon-content');

    const sku = skuInput ? skuInput.value.trim() : 'SKU-1001';
    if (!sku) return;

    if (inspectBtn) {
        inspectBtn.disabled = true;
        inspectBtn.innerText = '⏳ Evaluating...';
    }

    const host = window.location.hostname || 'localhost';
    const baseUrl = `${window.location.protocol}//${host}:8080`;

    try {
        const [priceRes, supplyRes, carbonRes] = await Promise.all([
            fetch(`${baseUrl}/api/v1/pricing/${sku}`).then(r => r.json()).catch(err => ({ error: String(err) })),
            fetch(`${baseUrl}/api/v1/inventory/availability/${sku}`).then(r => r.json()).catch(err => ({ error: String(err) })),
            fetch(`${baseUrl}/api/v1/carbon/${sku}`).then(r => r.json()).catch(err => ({ error: String(err) }))
        ]);

        // Render Pricing
        if (pricingContent) {
            if (priceRes.error) {
                pricingContent.innerHTML = `<p style="color: #ff5252;">Error: ${priceRes.error}</p>`;
            } else {
                pricingContent.innerHTML = `
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 4px; margin-bottom: 6px;">
                        <span style="color: #aaa;">Base Price:</span> <strong>$${priceRes.base_price}</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 4px; margin-bottom: 6px;">
                        <span style="color: #aaa;">Recommended:</span> <strong style="color: #00e676;">$${priceRes.recommended_price}</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 4px; margin-bottom: 6px;">
                        <span style="color: #aaa;">Discount / Adj:</span> <strong style="color: #ffab00;">${priceRes.discount_pct}%</strong>
                    </div>
                    <p style="background: rgba(0,0,0,0.4); padding: 8px; border-radius: 6px; font-size: 0.75rem; color: #80cbc4; margin-top: 8px;">
                        ${priceRes.reasoning}
                    </p>
                `;
            }
        }

        // Render Supply Chain
        if (supplyContent) {
            if (Array.isArray(supplyRes)) {
                let whHtml = `<div style="margin-bottom: 6px;"><strong>Active Warehouses:</strong> ${supplyRes.length}</div>`;
                supplyRes.forEach(wh => {
                    whHtml += `
                        <div style="background: rgba(0,0,0,0.4); padding: 8px; border-radius: 6px; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div style="font-weight: bold; color: #fff;">${wh.warehouse_name}</div>
                                <div style="font-size: 0.75rem; color: #888;">${wh.warehouse_city}</div>
                            </div>
                            <div style="text-align: right;">
                                <div style="font-weight: bold; color: #00e676;">${wh.quantity_available} units</div>
                                <div style="font-size: 0.75rem; color: #aaa;">C&C: ${wh.click_collect_ready ? 'Ready' : 'N/A'}</div>
                            </div>
                        </div>
                    `;
                });
                supplyContent.innerHTML = whHtml;
            } else {
                supplyContent.innerHTML = `<p style="color: #ff5252;">${supplyRes.error || 'No inventory records found'}</p>`;
            }
        }

        // Render Carbon
        if (carbonContent) {
            if (carbonRes.error) {
                carbonContent.innerHTML = `<p style="color: #ff5252;">Error: ${carbonRes.error}</p>`;
            } else {
                carbonContent.innerHTML = `
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 4px; margin-bottom: 6px;">
                        <span style="color: #aaa;">Total CO2e:</span> <strong style="color: #b388ff; font-size: 1.1rem;">${carbonRes.total_kg_co2e} kg</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 4px; margin-bottom: 6px;">
                        <span style="color: #aaa;">ESG Grade:</span> <strong style="background: #7c4dff; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;">Grade ${carbonRes.label}</strong>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; text-align: center; font-size: 0.75rem; margin-top: 8px;">
                        <div style="background: rgba(0,0,0,0.4); padding: 6px; border-radius: 4px;">
                            <div style="color: #888;">Scope 1</div>
                            <div><strong>${carbonRes.scope1_kg} kg</strong></div>
                        </div>
                        <div style="background: rgba(0,0,0,0.4); padding: 6px; border-radius: 4px;">
                            <div style="color: #888;">Scope 2</div>
                            <div><strong>${carbonRes.scope2_kg} kg</strong></div>
                        </div>
                        <div style="background: rgba(0,0,0,0.4); padding: 6px; border-radius: 4px;">
                            <div style="color: #888;">Scope 3</div>
                            <div><strong>${carbonRes.scope3_kg} kg</strong></div>
                        </div>
                    </div>
                `;
            }
        }
    } catch (e) {
        console.error('Project 2 Ontology query failed:', e);
    } finally {
        if (inspectBtn) {
            inspectBtn.disabled = false;
            inspectBtn.innerText = '🔍 Query Enterprise Ontology';
        }
    }
}
window.fetchProject2Ontology = fetchProject2Ontology;

// ==========================================
// Live Excel Data Sync (live_data/ .xlsx)
// ==========================================
async function triggerLiveExcelSync() {
    const btn = document.getElementById('btn-sync-excel');
    const statusVal = document.getElementById('excel-status-val');
    const lastSyncEl = document.getElementById('excel-last-sync');

    try {
        if (btn) {
            btn.innerHTML = '<span>🔄</span> Syncing...';
            btn.disabled = true;
        }
        if (statusVal) {
            statusVal.innerHTML = '<span style="color:#00e5ff;">Scanning live_data/...</span>';
        }

        const res = await fetch(`${state.apiUrl}/api/v1/sync/now`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || `Server responded with ${res.status}`);
        }

        const data = await res.json();

        if (data.status === 'SUCCESS' || data.status === 'SKIPPED') {
            const rowCount = data.rows_synced || 0;
            const filesCount = (data.files_processed || []).length;
            if (statusVal) {
                statusVal.innerHTML = `<span style="color:#00e676;">Synced (${rowCount} rows)</span>`;
            }
            if (lastSyncEl && data.synced_at) {
                const time = new Date(data.synced_at).toLocaleTimeString();
                lastSyncEl.innerText = `Synced at ${time} (${filesCount} files)`;
            }
            console.log(`[Excel Sync] Successfully synced ${rowCount} rows:`, data);
        } else {
            if (statusVal) {
                statusVal.innerHTML = `<span style="color:#ffab00;">${data.status || 'Failed'}</span>`;
            }
            if (data.errors && data.errors.length > 0 && lastSyncEl) {
                lastSyncEl.innerText = data.errors[0].slice(0, 45) + '...';
            }
        }

        // Refresh Auto Insights if available
        if (typeof window.loadAutoInsights === 'function') {
            window.loadAutoInsights();
        }
    } catch (err) {
        console.error('Excel sync error:', err);
        if (statusVal) {
            statusVal.innerHTML = `<span style="color:#ff5252;">Sync Failed</span>`;
        }
        if (lastSyncEl) {
            lastSyncEl.innerText = err.message ? err.message.slice(0, 40) : 'Check live_data folder';
        }
    } finally {
        if (btn) {
            btn.innerHTML = '<span>🔄</span> Sync Live Data Now';
            btn.disabled = false;
        }
    }
}
window.triggerLiveExcelSync = triggerLiveExcelSync;

// ==========================================
// Email Alert Notifications Controller
// ==========================================
async function loadEmailConfig() {
    const badge = document.getElementById('email-mode-badge');
    const senderInput = document.getElementById('email-sender-input');
    const receiverInput = document.getElementById('email-receiver-input');
    const serverInput = document.getElementById('email-smtp-server');
    const portInput = document.getElementById('email-smtp-port');
    const feedback = document.getElementById('email-config-feedback');

    try {
        const res = await fetch(`${state.apiUrl}/api/v1/insights/email/status`);
        if (!res.ok) return;
        const data = await res.json();

        if (senderInput && data.sender_email && data.sender_email !== 'Not configured') {
            senderInput.value = data.sender_email;
        }
        if (receiverInput && data.recipients && data.recipients.length > 0) {
            receiverInput.value = data.recipients.join(', ');
        }
        if (serverInput && data.smtp_server && data.smtp_server !== 'Not configured') {
            serverInput.value = data.smtp_server;
        }
        if (portInput && data.smtp_port) {
            portInput.value = data.smtp_port;
        }

        if (badge) {
            if (data.is_configured) {
                badge.innerText = 'ACTIVE SMTP';
                badge.style.background = 'rgba(0, 230, 118, 0.2)';
                badge.style.color = '#00e676';
                badge.style.borderColor = 'rgba(0, 230, 118, 0.4)';
            } else {
                badge.innerText = 'LOG FALLBACK';
                badge.style.background = 'rgba(255, 171, 0, 0.2)';
                badge.style.color = '#ffab00';
                badge.style.borderColor = 'rgba(255, 171, 0, 0.4)';
            }
        }
    } catch (err) {
        console.warn('Could not load email configuration:', err);
    }
}
window.loadEmailConfig = loadEmailConfig;

async function saveEmailConfig() {
    const btn = document.getElementById('btn-save-email-config');
    const senderInput = document.getElementById('email-sender-input');
    const passInput = document.getElementById('email-password-input');
    const receiverInput = document.getElementById('email-receiver-input');
    const serverInput = document.getElementById('email-smtp-server');
    const portInput = document.getElementById('email-smtp-port');
    const feedback = document.getElementById('email-config-feedback');
    const badge = document.getElementById('email-mode-badge');

    const sender = (senderInput?.value || '').trim();
    const pass = (passInput?.value || '').trim();
    const receiver = (receiverInput?.value || '').trim();
    const server = (serverInput?.value || '').trim();
    const port = parseInt(portInput?.value || '587');

    if (!sender && !receiver) {
        if (feedback) {
            feedback.innerHTML = '<span style="color:#ff5252;">⚠️ Please enter sender or receiver email</span>';
        }
        return;
    }

    try {
        if (btn) {
            btn.innerHTML = '<span>⏳</span> Saving...';
            btn.disabled = true;
        }

        const res = await fetch(`${state.apiUrl}/api/v1/insights/email/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sender_email: sender || null,
                sender_password: pass || null,
                receiver_emails: receiver || null,
                smtp_server: server || null,
                smtp_port: isNaN(port) ? null : port
            })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || 'Failed to save email settings');
        }

        if (passInput) passInput.value = ''; // clear password field for security

        const currentStatus = data.current_status || {};
        if (badge) {
            if (currentStatus.is_configured) {
                badge.innerText = 'ACTIVE SMTP';
                badge.style.background = 'rgba(0, 230, 118, 0.2)';
                badge.style.color = '#00e676';
                badge.style.borderColor = 'rgba(0, 230, 118, 0.4)';
            } else {
                badge.innerText = 'LOG FALLBACK';
                badge.style.background = 'rgba(255, 171, 0, 0.2)';
                badge.style.color = '#ffab00';
                badge.style.borderColor = 'rgba(255, 171, 0, 0.4)';
            }
        }

        if (feedback) {
            feedback.innerHTML = `<span style="color:#00e676;">✓ Settings saved! (${currentStatus.mode || 'Ready'})</span>`;
            setTimeout(() => { feedback.innerHTML = ''; }, 4500);
        }
    } catch (err) {
        console.error('Error saving email config:', err);
        if (feedback) {
            feedback.innerHTML = `<span style="color:#ff5252;">✗ Error: ${err.message}</span>`;
        }
    } finally {
        if (btn) {
            btn.innerHTML = '<span>💾</span> Save';
            btn.disabled = false;
        }
    }
}
window.saveEmailConfig = saveEmailConfig;

async function testEmailAlert() {
    const btn = document.getElementById('btn-test-email-alert');
    const senderInput = document.getElementById('email-sender-input');
    const passInput = document.getElementById('email-password-input');
    const receiverInput = document.getElementById('email-receiver-input');
    const serverInput = document.getElementById('email-smtp-server');
    const portInput = document.getElementById('email-smtp-port');
    const feedback = document.getElementById('email-config-feedback');
    const badge = document.getElementById('email-mode-badge');

    const sender = (senderInput?.value || '').trim();
    const pass = (passInput?.value || '').trim();
    const receiver = (receiverInput?.value || '').trim();
    const server = (serverInput?.value || '').trim();
    const port = parseInt(portInput?.value || '587');

    try {
        if (btn) {
            btn.innerHTML = '<span>⏳</span> Sending...';
            btn.disabled = true;
        }
        if (feedback) {
            feedback.innerHTML = '<span style="color:#00e5ff;">Testing email connection...</span>';
        }

        const res = await fetch(`${state.apiUrl}/api/v1/insights/email/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sender_email: sender || null,
                sender_password: pass || null,
                receiver_emails: receiver || null,
                smtp_server: server || null,
                smtp_port: isNaN(port) ? null : port
            })
        });

        const data = await res.json();

        if (data.details && badge) {
            if (data.details.is_configured) {
                badge.innerText = 'ACTIVE SMTP';
                badge.style.background = 'rgba(0, 230, 118, 0.2)';
                badge.style.color = '#00e676';
                badge.style.borderColor = 'rgba(0, 230, 118, 0.4)';
            } else {
                badge.innerText = 'LOG FALLBACK';
                badge.style.background = 'rgba(255, 171, 0, 0.2)';
                badge.style.color = '#ffab00';
                badge.style.borderColor = 'rgba(255, 171, 0, 0.4)';
            }
        }

        if (data.dispatched) {
            if (feedback) {
                feedback.innerHTML = `<span style="color:#00e676; font-weight:600;">✓ Test email sent successfully to ${receiver || 'recipient'}!</span>`;
            }
        } else {
            if (feedback) {
                const msg = data.message || 'Logged to system fallback';
                feedback.innerHTML = `<span style="color:#ffab00; font-size:0.75rem; line-height:1.3; display:block;">⚠️ ${msg}</span>`;
            }
        }
    } catch (err) {
        console.error('Test email error:', err);
        if (feedback) {
            feedback.innerHTML = `<span style="color:#ff5252;">✗ Test failed: ${err.message}</span>`;
        }
    } finally {
        if (btn) {
            btn.innerHTML = '<span>✉️</span> Test Send';
            btn.disabled = false;
        }
    }
}
window.testEmailAlert = testEmailAlert;

function focusEmailSettings() {
    const section = document.getElementById('email-notifications-section');
    const senderInput = document.getElementById('email-sender-input');
    if (section) {
        section.scrollIntoView({ behavior: 'smooth', block: 'center' });
        section.style.boxShadow = '0 0 25px rgba(0, 229, 255, 0.5)';
        section.style.borderColor = '#00e5ff';
        setTimeout(() => {
            section.style.boxShadow = '';
            section.style.borderColor = '';
        }, 2000);
    }
    if (senderInput) {
        setTimeout(() => senderInput.focus(), 300);
    }
}
window.focusEmailSettings = focusEmailSettings;

// Load email configuration on page initialization
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadEmailConfig);
} else {
    loadEmailConfig();
}



