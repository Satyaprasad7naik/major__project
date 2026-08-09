// ===========================
// Application State
// ===========================
const state = {
    apiUrl: 'http://localhost:8080',
    selectedDomain: 'general',
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

    // Update UI
    elements.domainBtns.forEach(btn => {
        if (btn.dataset.domain === domain) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
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
    handleDomainChange('general');

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

// Close export dropdown when clicking outside
document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('export-dropdown');
    const exportBtn = elements.exportBtn;
    if (dropdown && !dropdown.contains(e.target) && !exportBtn.contains(e.target)) {
        dropdown.classList.add('hidden');
    }
});
