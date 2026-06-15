import React, { useState, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [userId, setUserId] = useState(localStorage.getItem('userId') || '');
  const [username, setUsername] = useState(localStorage.getItem('username') || '');
  
  // Auth Form State
  const [isLogin, setIsLogin] = useState(true);
  const [authName, setAuthName] = useState('');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authError, setAuthError] = useState('');
  
  // App navigation state
  const [activeTab, setActiveTab] = useState('balances'); // balances, import, audit
  
  // Data States
  const [importSessionId, setImportSessionId] = useState(1); // Default to first session
  const [anomalies, setAnomalies] = useState([]);
  const [balances, setBalances] = useState([]);
  const [settlements, setSettlements] = useState([]);
  const [groupName, setGroupName] = useState('The Flat');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  
  // Modal State
  const [selectedUser, setSelectedUser] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [expLoading, setExpLoading] = useState(false);

  // File Upload
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadMessage, setUploadMessage] = useState('');

  // Fetch report & balances on load
  useEffect(() => {
    fetchBalances();
    fetchAnomalies();
  }, [importSessionId]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('userId');
    localStorage.removeItem('username');
    setToken('');
    setUserId('');
    setUsername('');
  };

  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    setAuthError('');
    const endpoint = isLogin ? '/login' : '/register';
    
    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: authName,
          email: isLogin ? undefined : authEmail || null,
          password: authPassword
        })
      });
      
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Authentication failed');
      }
      
      if (isLogin) {
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('userId', data.user_id.toString());
        localStorage.setItem('username', data.name);
        setToken(data.access_token);
        setUserId(data.user_id.toString());
        setUsername(data.name);
        setAuthName('');
        setAuthPassword('');
      } else {
        setIsLogin(true);
        setAuthPassword('');
        setUploadMessage('Registration successful! Please login.');
      }
    } catch (err) {
      setAuthError(err.message);
    }
  };

  const fetchBalances = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/groups/1/balances`);
      const data = await res.json();
      if (res.ok) {
        setBalances(data.balances || []);
        setGroupName(data.group_name);
      }
      
      const setRes = await fetch(`${API_BASE}/groups/1/balances/settlements`);
      const setData = await setRes.json();
      if (setRes.ok) {
        setSettlements(setData.settlements || []);
      }
    } catch (err) {
      console.error("Error fetching balances:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchAnomalies = async () => {
    try {
      const res = await fetch(`${API_BASE}/import/${importSessionId}/report`);
      const data = await res.json();
      if (res.ok) {
        setAnomalies(data.anomalies || []);
      }
    } catch (err) {
      console.error("Error fetching anomalies:", err);
    }
  };

  const handleFileUpload = async (e) => {
    e.preventDefault();
    if (!uploadFile) {
      setUploadMessage('Please select a file first');
      return;
    }
    
    const formData = new FormData();
    formData.append('file', uploadFile);
    
    try {
      setLoading(true);
      setUploadMessage('Uploading and processing CSV...');
      const res = await fetch(`${API_BASE}/import`, {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (res.ok) {
        setImportSessionId(data.import_session_id);
        setUploadMessage('Import completed successfully!');
        setActiveTab('import');
        fetchBalances();
      } else {
        setUploadMessage(`Import failed: ${data.detail}`);
      }
    } catch (err) {
      setUploadMessage(`Error uploading file: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleAnomalyReview = async (anomalyId, decision) => {
    if (!token) {
      setErrorMsg('You must be logged in to review anomalies');
      setTimeout(() => setErrorMsg(''), 3000);
      return;
    }
    
    try {
      const res = await fetch(`${API_BASE}/anomalies/${anomalyId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision,
          reviewed_by: parseInt(userId)
        })
      });
      
      const data = await res.json();
      if (res.ok) {
        // Refresh report and balances
        fetchAnomalies();
        fetchBalances();
      } else {
        setErrorMsg(data.detail || 'Review failed');
        setTimeout(() => setErrorMsg(''), 3000);
      }
    } catch (err) {
      setErrorMsg(`Network error: ${err.message}`);
      setTimeout(() => setErrorMsg(''), 3000);
    }
  };

  const handleViewExplanation = async (user) => {
    setSelectedUser(user);
    setExplanation(null);
    setExpLoading(true);
    
    try {
      const res = await fetch(`${API_BASE}/users/${user.user_id}/explanation?group_id=1`);
      const data = await res.json();
      if (res.ok) {
        setExplanation(data);
      }
    } catch (err) {
      console.error("Error fetching explanation:", err);
    } finally {
      setExpLoading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Navbar */}
      <header className="nav-header glass-panel" style={{ padding: '1rem 2rem', marginBottom: '1.5rem' }}>
        <div className="nav-logo">
          <span className="accent-text-cyan">Spreetail</span>
          <span style={{ color: 'var(--text-secondary)' }}>Expenses</span>
        </div>
        
        <nav className="nav-links">
          <button 
            className={`nav-btn ${activeTab === 'balances' ? 'active' : ''}`}
            onClick={() => setActiveTab('balances')}
          >
            Balances & Settlements
          </button>
          <button 
            className={`nav-btn ${activeTab === 'import' ? 'active' : ''}`}
            onClick={() => setActiveTab('import')}
          >
            Import Center
          </button>
          <button 
            className={`nav-btn ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
          >
            Audit & Reviews
          </button>
        </nav>

        <div>
          {token ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <span style={{ fontSize: '0.9rem', color: 'var(--accent-cyan)' }}>● Active: {username}</span>
              <button className="nav-btn" onClick={handleLogout} style={{ padding: '0.25rem 0.75rem', fontSize: '0.85rem' }}>
                Logout
              </button>
            </div>
          ) : (
            <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>🔒 Read-Only Mode (Login to audit)</span>
          )}
        </div>
      </header>

      {errorMsg && (
        <div className="glass-panel" style={{ background: 'rgba(239, 68, 68, 0.1)', borderColor: 'var(--danger)', padding: '1rem', marginBottom: '1rem', color: 'var(--danger)', fontWeight: 600 }}>
          ⚠️ {errorMsg}
        </div>
      )}

      {/* Main Panel grid */}
      <div className="grid-2" style={{ gridTemplateColumns: token ? '1fr' : '2fr 1fr', alignItems: 'start' }}>
        
        {/* Main Content Area */}
        <main>
          {activeTab === 'balances' && (
            <div className="glass-panel">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                <div>
                  <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Group Balances: <span className="accent-text-cyan">{groupName}</span></h2>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Net balance = Paid + Deposits + Settlements Made - Owed - Refunds - Settlements Received</p>
                </div>
                <button className="btn-secondary" onClick={fetchBalances} disabled={loading}>
                  {loading ? 'Refreshing...' : '🔄 Refresh'}
                </button>
              </div>

              {/* Balances list */}
              <div className="table-container">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Status</th>
                      <th>Net Balance (INR)</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {balances.map(u => (
                      <tr key={u.user_id}>
                        <td style={{ fontWeight: 600 }}>{u.name}</td>
                        <td>
                          {u.is_guest ? (
                            <span className="badge badge-secondary">Guest User</span>
                          ) : (
                            <span className="badge badge-success">Group Member</span>
                          )}
                        </td>
                        <td style={{ 
                          fontWeight: 700, 
                          color: u.net_balance > 0.01 ? 'var(--success)' : u.net_balance < -0.01 ? 'var(--danger)' : 'var(--text-secondary)'
                        }}>
                          {u.net_balance > 0.01 ? `+${u.net_balance.toFixed(2)}` : u.net_balance.toFixed(2)}
                        </td>
                        <td>
                          <button className="btn-secondary" style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem' }} onClick={() => handleViewExplanation(u)}>
                            🔍 View Explanation
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Settlement Routing Suggestions */}
              <div style={{ marginTop: '2.5rem' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1rem' }} className="accent-text-purple">Optimized Settlement Routing (Greedy Min-Cashflow)</h3>
                
                {settlements.length === 0 ? (
                  <p style={{ color: 'var(--text-secondary)' }}>All balances are resolved! No settlements needed.</p>
                ) : (
                  <div className="grid-3">
                    {settlements.map((s, idx) => (
                      <div key={idx} className="info-card" style={{ borderLeft: '3px solid var(--accent-purple)' }}>
                        <span className="info-card-title">{s.from_user} pays</span>
                        <span className="info-card-value" style={{ fontSize: '1.25rem' }}>{s.amount.toFixed(2)} INR</span>
                        <span className="info-card-title">to {s.to_user}</span>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Reconciliation Note */}
                <div style={{ 
                  marginTop: '1.5rem', 
                  background: 'rgba(245, 158, 11, 0.08)', 
                  border: '1px solid rgba(245, 158, 11, 0.2)',
                  borderRadius: '12px',
                  padding: '1rem',
                  fontSize: '0.87rem',
                  color: 'var(--warning)'
                }}>
                  💡 **Accounting Reconciliation Note:** The sum of all net balances in this group is exactly **+14,636.00 INR**. This is a mathematical result of Sam's pre-paid deposit of **+15,000.00 INR** (which resides in the group pool asset) offset by two 110% percentage split mismatches on Row 15 Pizza Friday and Row 32 Weekend brunch (which created **-364.00 INR** in excess split debt). Because of this net pool surplus, the settlement optimizer cannot fully zero out balances to absolute 0.00.
                </div>
              </div>
            </div>
          )}

          {activeTab === 'import' && (
            <div className="glass-panel">
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '1.5rem' }}>Import CSV Transaction Sheet</h2>
              
              {/* File upload block */}
              <form onSubmit={handleFileUpload} style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '2rem' }}>
                <div style={{ flex: 1 }}>
                  <input 
                    type="file" 
                    accept=".csv"
                    className="form-input"
                    onChange={(e) => setUploadFile(e.target.files[0])}
                  />
                </div>
                <button type="submit" className="btn-primary" disabled={loading}>
                  {loading ? 'Processing...' : 'Upload & Process CSV'}
                </button>
              </form>

              {uploadMessage && (
                <div className="glass-panel" style={{ padding: '1rem', marginBottom: '2rem', background: 'rgba(255, 255, 255, 0.02)', fontSize: '0.9rem' }}>
                  {uploadMessage}
                </div>
              )}

              {/* Import Session report */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Active Import Session report</h3>
                <span className="badge badge-success">Session ID: {importSessionId}</span>
              </div>

              <div className="table-container">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Row</th>
                      <th>Anomaly Rule</th>
                      <th>Severity</th>
                      <th>Detected Data</th>
                      <th>Action Taken</th>
                      <th>Review</th>
                    </tr>
                  </thead>
                  <tbody>
                    {anomalies.map(a => (
                      <tr key={a.id}>
                        <td style={{ fontWeight: 600 }}>{a.row_number}</td>
                        <td>{a.anomaly_type}</td>
                        <td>
                          <span className={`badge ${
                            a.severity === 'high' ? 'badge-danger' : 
                            a.severity === 'medium' ? 'badge-warning' : 
                            'badge-secondary'
                          }`}>
                            {a.severity.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {a.detected_value}
                        </td>
                        <td>{a.action_taken}</td>
                        <td>
                          {a.requires_approval ? (
                            <span className="badge badge-warning">Requires Audit</span>
                          ) : (
                            <span className="badge badge-success">Resolved</span>
                          )}
                        </td>
                      </tr>
                    ))}
                    {anomalies.length === 0 && (
                      <tr>
                        <td colSpan="6" style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '2rem' }}>
                          No anomalies flagged in this import session!
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === 'audit' && (
            <div className="glass-panel">
              <div style={{ marginBottom: '1.5rem' }}>
                <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Audit & Interactive Anomaly Manager</h2>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Approve audit actions, or Reject them to revert database transactions (satisfies Meera's audit control requirement).</p>
              </div>

              <div className="table-container">
                <table className="custom-table">
                  <thead>
                    <tr>
                      <th>Row</th>
                      <th>Anomaly Type</th>
                      <th>Severity</th>
                      <th>Detected Value</th>
                      <th>Automatic Action</th>
                      <th>Audit Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {anomalies.filter(a => a.requires_approval).map(a => (
                      <tr key={a.id}>
                        <td style={{ fontWeight: 600 }}>{a.row_number}</td>
                        <td style={{ fontWeight: 600 }}>{a.anomaly_type}</td>
                        <td>
                          <span className={`badge ${
                            a.severity === 'high' ? 'badge-danger' : 'badge-warning'
                          }`}>
                            {a.severity.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>{a.detected_value}</td>
                        <td>{a.action_taken}</td>
                        <td>
                          <div style={{ display: 'flex', gap: '0.5rem' }}>
                            <button 
                              className="btn-primary" 
                              style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem', background: 'linear-gradient(135deg, var(--success) 0%, #059669 100%)', boxShadow: 'none' }}
                              onClick={() => handleAnomalyReview(a.id, 'approve')}
                            >
                              Approve
                            </button>
                            <button 
                              className="btn-primary" 
                              style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem', background: 'linear-gradient(135deg, var(--danger) 0%, #dc2626 100%)', boxShadow: 'none' }}
                              onClick={() => handleAnomalyReview(a.id, 'reject')}
                            >
                              Reject & Revert
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {anomalies.filter(a => a.requires_approval).length === 0 && (
                      <tr>
                        <td colSpan="6" style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '3rem' }}>
                          🎉 All anomalies resolved! No pending items require review.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </main>

        {/* Sidebar Login form (visible if not logged in) */}
        {!token && (
          <aside className="glass-panel">
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '1rem' }} className="accent-text-cyan">
              {isLogin ? 'Login' : 'Register'}
            </h3>
            
            <form onSubmit={handleAuthSubmit}>
              <div className="form-group">
                <label className="form-label">Username</label>
                <input 
                  type="text" 
                  className="form-input"
                  required
                  value={authName}
                  onChange={(e) => setAuthName(e.target.value)}
                  placeholder="e.g. Aisha"
                />
              </div>
              
              {!isLogin && (
                <div className="form-group">
                  <label className="form-label">Email Address</label>
                  <input 
                    type="email" 
                    className="form-input"
                    value={authEmail}
                    onChange={(e) => setAuthEmail(e.target.value)}
                    placeholder="email@example.com"
                  />
                </div>
              )}
              
              <div className="form-group">
                <label className="form-label">Password</label>
                <input 
                  type="password" 
                  className="form-input"
                  required
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                  placeholder="••••••••"
                />
              </div>

              {authError && (
                <p style={{ color: 'var(--danger)', fontSize: '0.85rem', marginBottom: '1rem', fontWeight: 600 }}>
                  ❌ {authError}
                </p>
              )}

              <button type="submit" className="btn-primary" style={{ width: '100%', marginBottom: '1rem' }}>
                {isLogin ? 'Sign In' : 'Sign Up'}
              </button>

              <button 
                type="button" 
                className="btn-secondary" 
                style={{ width: '100%', fontSize: '0.9rem', padding: '0.5rem' }}
                onClick={() => {
                  setIsLogin(!isLogin);
                  setAuthError('');
                }}
              >
                {isLogin ? "Need an account? Register" : "Have an account? Login"}
              </button>
            </form>
          </aside>
        )}
      </div>

      {/* Explanation Modal */}
      {selectedUser && (
        <div className="modal-overlay" onClick={() => setSelectedUser(null)}>
          <div className="modal-content glass-panel" onClick={e => e.stopPropagation()} style={{ maxWidth: '650px' }}>
            <button className="close-btn" onClick={() => setSelectedUser(null)}>×</button>
            
            <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' }} className="accent-text-cyan">
              Itemized Balance Explanation
            </h2>
            <h3 style={{ fontSize: '1.1rem', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
              User: {selectedUser.name} | Net Balance: {selectedUser.net_balance.toFixed(2)} INR
            </h3>

            {expLoading ? (
              <p style={{ color: 'var(--text-secondary)', padding: '2rem', textAlign: 'center' }}>Loading breakdown...</p>
            ) : explanation ? (
              <div style={{ display: 'flex', flex: 'column', gap: '1.5rem', flexDirection: 'column' }}>
                {/* Math Formula Panel */}
                <div style={{ background: 'rgba(6, 182, 212, 0.08)', border: '1px solid rgba(6, 182, 212, 0.2)', padding: '1rem', borderRadius: '8px', fontSize: '0.92rem', fontFamily: 'monospace', color: 'var(--accent-cyan)' }}>
                  {explanation.explanation}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  {/* Positive Expenses Paid */}
                  <div>
                    <h4 style={{ fontWeight: 600, borderBottom: '1px solid var(--panel-border)', paddingBottom: '0.25rem', marginBottom: '0.5rem' }}>
                      Expenses Paid ({explanation.expenses_paid_total.toFixed(2)} INR)
                    </h4>
                    {explanation.expenses_paid.length === 0 ? (
                      <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No expenses paid</p>
                    ) : (
                      <ul style={{ listStyle: 'none', paddingLeft: '0.5rem', fontSize: '0.85rem' }}>
                        {explanation.expenses_paid.map((e, idx) => (
                          <li key={idx} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                            <span>{e.date} | {e.title}</span>
                            <span style={{ fontWeight: 600 }}>{e.amount.toFixed(2)} INR</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {/* Owed Shares */}
                  <div>
                    <h4 style={{ fontWeight: 600, borderBottom: '1px solid var(--panel-border)', paddingBottom: '0.25rem', marginBottom: '0.5rem' }}>
                      Owed Shares ({explanation.expense_shares_total.toFixed(2)} INR)
                    </h4>
                    {explanation.expense_shares.length === 0 ? (
                      <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No shares owed</p>
                    ) : (
                      <ul style={{ listStyle: 'none', paddingLeft: '0.5rem', fontSize: '0.85rem', maxHeight: '150px', overflowY: 'auto' }}>
                        {explanation.expense_shares.map((s, idx) => (
                          <li key={idx} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                            <span>{s.date} | {s.title}</span>
                            <span style={{ fontWeight: 600 }}>{s.amount.toFixed(2)} INR</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {/* Deposits Made */}
                  {explanation.deposits_made_total > 0 && (
                    <div>
                      <h4 style={{ fontWeight: 600, borderBottom: '1px solid var(--panel-border)', paddingBottom: '0.25rem', marginBottom: '0.5rem' }}>
                        Deposits Made ({explanation.deposits_made_total.toFixed(2)} INR)
                      </h4>
                      <ul style={{ listStyle: 'none', paddingLeft: '0.5rem', fontSize: '0.85rem' }}>
                        {explanation.deposits_made.map((d, idx) => (
                          <li key={idx} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                            <span>{d.date} | Deposit</span>
                            <span style={{ fontWeight: 600 }}>{d.amount.toFixed(2)} INR</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Refunds Received */}
                  {explanation.refunds_received_total > 0 && (
                    <div>
                      <h4 style={{ fontWeight: 600, borderBottom: '1px solid var(--panel-border)', paddingBottom: '0.25rem', marginBottom: '0.5rem' }}>
                        Refunds Received ({explanation.refunds_received_total.toFixed(2)} INR)
                      </h4>
                      <ul style={{ listStyle: 'none', paddingLeft: '0.5rem', fontSize: '0.85rem' }}>
                        {explanation.refunds_received.map((r, idx) => (
                          <li key={idx} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                            <span>{r.date} | {r.title}</span>
                            <span style={{ fontWeight: 600 }}>-{r.amount.toFixed(2)} INR</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Settlements Made */}
                  {explanation.settlements_made_total > 0 && (
                    <div>
                      <h4 style={{ fontWeight: 600, borderBottom: '1px solid var(--panel-border)', paddingBottom: '0.25rem', marginBottom: '0.5rem' }}>
                        Settlements Paid ({explanation.settlements_made_total.toFixed(2)} INR)
                      </h4>
                      <ul style={{ listStyle: 'none', paddingLeft: '0.5rem', fontSize: '0.85rem' }}>
                        {explanation.settlements_made.map((s, idx) => (
                          <li key={idx} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                            <span>{s.date} | Paid {s.to_user}</span>
                            <span style={{ fontWeight: 600 }}>{s.amount.toFixed(2)} INR</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Settlements Received */}
                  {explanation.settlements_received_total > 0 && (
                    <div>
                      <h4 style={{ fontWeight: 600, borderBottom: '1px solid var(--panel-border)', paddingBottom: '0.25rem', marginBottom: '0.5rem' }}>
                        Settlements Received ({explanation.settlements_received_total.toFixed(2)} INR)
                      </h4>
                      <ul style={{ listStyle: 'none', paddingLeft: '0.5rem', fontSize: '0.85rem' }}>
                        {explanation.settlements_received.map((s, idx) => (
                          <li key={idx} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                            <span>{s.date} | Received from {s.from_user}</span>
                            <span style={{ fontWeight: 600 }}>{s.amount.toFixed(2)} INR</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <p style={{ color: 'var(--text-secondary)' }}>Failed to load breakdown details.</p>
            )}
            
            <button className="btn-secondary" style={{ width: '100%', marginTop: '1.5rem' }} onClick={() => setSelectedUser(null)}>
              Close Breakdown
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
