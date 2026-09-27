import React, { useEffect, useState } from 'react';
import './AutoInsightsPanel.css';

export interface AutoInsight {
  id: number | string;
  type: string;
  title: string;
  description: string;
  severity: 'high' | 'medium' | 'low' | 'critical' | string;
  product_id?: string | number | null;
  product_name?: string | null;
  created_at: string;
  is_read: boolean;
}

interface AutoInsightsPanelProps {
  apiBaseUrl?: string;
  domain?: string;
  onInsightClick?: (insight: AutoInsight) => void;
}

export const AutoInsightsPanel: React.FC<AutoInsightsPanelProps> = ({
  apiBaseUrl = '/api/v1',
  domain = 'retail_clothing',
  onInsightClick,
}) => {
  const [insights, setInsights] = useState<AutoInsight[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchInsights = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/insights/today?domain=${domain}`);
      if (!res.ok) {
        throw new Error(`Failed to fetch insights (${res.status})`);
      }
      const data = await res.json();
      setInsights(data.insights || []);
    } catch (err: any) {
      setError(err.message || 'Error loading auto-insights');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInsights();
  }, [domain, apiBaseUrl]);

  const handleMarkAsRead = async (e: React.MouseEvent, id: number | string) => {
    e.stopPropagation();
    try {
      const res = await fetch(`${apiBaseUrl}/insights/${id}/read`, {
        method: 'PATCH',
      });
      if (res.ok) {
        setInsights((prev) =>
          prev.map((item) => (item.id === id ? { ...item, is_read: true } : item))
        );
      }
    } catch (err) {
      console.error('Failed to mark insight as read', err);
    }
  };

  const getSeverityBadgeClass = (severity: string) => {
    const sev = severity.toLowerCase();
    if (sev === 'high' || sev === 'critical') {
      return 'severity-high';
    }
    if (sev === 'medium') {
      return 'severity-medium';
    }
    return 'severity-low';
  };

  return (
    <div className="auto-insights-container">
      <div className="auto-insights-header">
        <div className="title-group">
          <span className="insights-icon">💡</span>
          <h3>Auto Insights</h3>
          <span className="count-badge">{insights.filter((i) => !i.is_read).length} Unread</span>
        </div>
        <button className="refresh-btn" onClick={fetchInsights} title="Refresh Insights">
          🔄
        </button>
      </div>

      {loading && (
        <div className="insights-loading">
          <div className="spinner"></div>
          <span>Scanning inventory & sales signals...</span>
        </div>
      )}

      {error && (
        <div className="insights-error">
          ⚠️ {error}
        </div>
      )}

      {!loading && !error && insights.length === 0 && (
        <div className="insights-empty">
          <p>🎉 No critical inventory or sales warnings today!</p>
        </div>
      )}

      {!loading && !error && (
        <div className="insights-list">
          {insights.map((insight) => {
            const sevClass = getSeverityBadgeClass(insight.severity);
            return (
              <div
                key={insight.id}
                className={`insight-card ${sevClass} ${insight.is_read ? 'is-read' : ''}`}
                onClick={() => onInsightClick && onInsightClick(insight)}
              >
                <div className="card-top">
                  <div className="card-title-row">
                    <h4 className="insight-title">{insight.title}</h4>
                    <span className={`severity-tag ${sevClass}`}>
                      {insight.severity.toUpperCase()}
                    </span>
                  </div>
                </div>

                <p className="insight-description">{insight.description}</p>

                <div className="card-bottom">
                  {insight.product_name && (
                    <span className="product-badge">
                      📦 {insight.product_name}
                    </span>
                  )}
                  <span className="time-stamp">
                    {new Date(insight.created_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>

                  {!insight.is_read && (
                    <button
                      className="mark-read-btn"
                      onClick={(e) => handleMarkAsRead(e, insight.id)}
                      title="Mark as read"
                    >
                      ✓ Mark read
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default AutoInsightsPanel;
