"""Self-contained Image Manager web UI (no external assets), served at GET /.

Unified single-page app, dashboard-first: Dashboard (KPIs + live artifact
status) | Upload | URL Import | Settings. Cable-map / Nokia EDA design
language: dark/light theme, branded logo + favicon, KPI overview cards,
adaptive live polling (4s while work is in flight, 12s at rest, paused when
the tab is hidden). Sign-in is silent SSO against the EDA Keycloak session
(new tab from the dashboard or embedded iframe), falling back to the OIDC
redirect flow; role gating via ALLOWED_ROLES (EDA ClusterRole)."""

SILENT_SSO_HTML = r"""<!doctype html><html><body><script>
parent.postMessage(location.href, location.origin);
</script></body></html>"""

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="imagemanager-api-base" content="/core/httpproxy/v1/imagemanager">
<title>EDA Image Manager</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%234092ff'/%3E%3Cstop offset='1' stop-color='%23005adf'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='32' height='32' rx='7' fill='url(%23g)'/%3E%3Cpath d='M16 5.5l9 5-9 5-9-5 9-5z' fill='%23fff'/%3E%3Cpath d='M7 16.5l9 5 9-5' stroke='%23fff' stroke-width='2' fill='none' opacity='.72' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpath d='M7 21.5l9 5 9-5' stroke='%23fff' stroke-width='2' fill='none' opacity='.42' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<style>
  :root {
    --eda-blue-100:#e4f0ff; --eda-blue-400:#4092ff; --eda-blue-500:#005aff; --eda-blue-600:#005adf;
    --eda-green-400:#63e194; --eda-green-500:#37cc73; --eda-green-700:#089b2a;
    --eda-yellow-400:#ffd568; --eda-yellow-500:#f7b737; --eda-yellow-600:#d98c0f;
    --eda-red-400:#f26c69; --eda-red-500:#e23b3b; --eda-teal-400:#50c4d0;
    --bg:#0f1419; --surface:#121c2a; --panel:#1a2332; --panel2:#222c39; --input-bg:#1a2332;
    --line:#2a3548; --line-soft:rgba(74,83,97,.45); --fg:#e6edf3; --muted:#8b98a6;
    --accent:var(--eda-blue-500); --accent2:var(--eda-blue-400); --accent-soft:rgba(0,90,255,.12);
    --state:rgba(0,90,255,.08); --state-strong:rgba(0,90,255,.16); --row-hover:rgba(255,255,255,.035);
    --row-stripe:rgba(255,255,255,.018);
    --ok-fg:#5ee58b; --ok-bg:rgba(55,204,115,.14); --ok-bd:rgba(55,204,115,.45);
    --info-fg:#90b7ff; --info-bg:rgba(0,90,255,.14); --info-bd:rgba(64,146,255,.45);
    --warn-fg:#ffd568; --warn-bg:rgba(247,183,55,.14); --warn-bd:rgba(247,183,55,.45);
    --err-fg:#ff9b9b; --err-bg:rgba(226,59,59,.16); --err-bd:rgba(242,108,105,.45);
    --danger:#e5484d; --danger-strong:#ff5c61; --on-danger:#fff;
    --neutral-fg:#abb4c2; --neutral-bg:rgba(171,180,194,.10); --neutral-bd:#3a4452;
    --snack-bg:#1a2332; --snack-fg:#e6edf3; --snack-action:#90b7ff;
    --scrim:rgba(0,0,0,.62);
    --radius-sm:6px; --radius-md:10px; --radius-lg:12px;
    --shadow-sm:0 1px 2px rgba(0,0,0,.35); --shadow-md:0 4px 16px rgba(0,0,0,.35);
    --shadow-lg:0 12px 32px rgba(0,0,0,.45);
    --transition:180ms cubic-bezier(.4,0,.2,1);
    color-scheme:dark;
  }
  html[data-theme="light"] {
    --bg:#e7ecf2; --surface:#f3f6fa; --panel:#fff; --panel2:#f2f4f8; --input-bg:#fff;
    --line:#bcc5d2; --line-soft:rgba(188,197,210,.65); --fg:#0b1119; --muted:#4a5563;
    --accent:var(--eda-blue-500); --accent2:var(--eda-blue-600); --accent-soft:#e4f0ff;
    --state:rgba(0,90,255,.06); --state-strong:rgba(0,90,255,.12); --row-hover:rgba(0,90,255,.045);
    --row-stripe:rgba(0,0,0,.02);
    --ok-fg:#089b2a; --ok-bg:#e4ffec; --ok-bd:#37cc73;
    --info-fg:#005adf; --info-bg:#e4f0ff; --info-bd:#4092ff;
    --warn-fg:#b06205; --warn-bg:#fff7d3; --warn-bd:#f7b737;
    --err-fg:#c91514; --err-bg:#ffe6e4; --err-bd:#e23b3b;
    --danger:#e23b3b; --danger-strong:#c91514; --on-danger:#fff;
    --neutral-fg:#687282; --neutral-bg:#eef0f3; --neutral-bd:#cfcfcf;
    --snack-bg:#2b303a; --snack-fg:#f3f5f8; --snack-action:#9cc0ff;
    --scrim:rgba(16,24,36,.46);
    color-scheme:light;
  }
  * { box-sizing:border-box; }
  html, body { min-height:100%; }
  body {
    margin:0; background:var(--bg); color:var(--fg);
    font:14px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
    -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
  }
  html.eda-embedded { --bg:#121c2a; --surface:#121c2a; }
  html.eda-embedded body { min-height:100vh; }

  .ripple { position:relative; overflow:hidden; }
  .ripple-ink { position:absolute; border-radius:50%; background:currentColor; opacity:.22;
    transform:scale(0); pointer-events:none; animation:ink .55s cubic-bezier(.4,0,.2,1); }
  @keyframes ink { to { transform:scale(1); opacity:0; } }
  @keyframes fadeIn { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:none; } }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
  @keyframes badgePop { 0%{transform:scale(1)} 50%{transform:scale(1.15)} 100%{transform:scale(1)} }
  @keyframes indet { 0%{margin-left:-42%} 100%{margin-left:102%} }

  /* AppBar — cable-map MUI AppBar parity (dense, flat, border-only) */
  .appbar {
    position:sticky; top:0; z-index:30; height:52px; padding:0 16px 0 18px;
    background:var(--surface); border-bottom:1px solid var(--line);
    display:flex; align-items:center; gap:16px; flex-shrink:0;
  }
  .brand { display:flex; align-items:center; gap:10px; min-width:0; flex:1 1 auto; }
  .brand-logo {
    width:28px; height:28px; flex:none; display:flex; align-items:center; justify-content:center;
    border-radius:6px; background:linear-gradient(145deg, var(--eda-blue-400), var(--eda-blue-600));
    box-shadow:0 0 0 1px rgba(0,90,255,.22);
  }
  .brand-logo svg { width:17px; height:17px; display:block; }
  .brand-text { display:flex; flex-direction:column; gap:1px; min-width:0; }
  .brand-row { display:flex; align-items:center; gap:8px; min-width:0; }
  .brand-name {
    font-size:15px; font-weight:500; letter-spacing:.015em; line-height:1.2; color:var(--fg);
  }
  .ver-badge {
    display:inline-flex; align-items:center; flex:none;
    padding:1px 7px; border-radius:999px;
    font-size:10px; font-weight:600; letter-spacing:.05em;
    font-family:var(--mono, ui-monospace, monospace);
    color:var(--accent); background:var(--accent-soft);
    border:1px solid color-mix(in srgb, var(--accent) 30%, transparent);
    line-height:1.5;
  }
  .brand-sub {
    font-size:11px; font-weight:400; color:var(--muted); line-height:1.25;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:min(440px, 42vw);
  }
  @media (max-width:720px){ .brand-sub { display:none; } }
  .appbar-actions { margin-left:auto; display:flex; align-items:center; gap:4px; flex:none; }
  .live-pill {
    display:inline-flex; align-items:center; gap:6px;
    padding:4px 10px 4px 8px; border-radius:999px;
    font-size:11px; font-weight:600; letter-spacing:.04em; text-transform:uppercase;
    color:var(--muted); background:var(--panel); border:1px solid var(--line);
    transition:color var(--transition), border-color var(--transition), background var(--transition);
  }
  .live-pill.active { color:var(--ok-fg); border-color:var(--ok-bd); background:var(--ok-bg); }
  .live-pill .live-dot {
    width:6px; height:6px; border-radius:50%; background:var(--muted); flex:none;
    transition:background var(--transition);
  }
  .live-pill.active .live-dot { background:var(--eda-green-500); animation:pulse 1.4s ease-in-out infinite; }
  @media (max-width:640px){ .live-pill .live-label { display:none; } }
  .user-chip {
    display:inline-flex; align-items:center; gap:8px;
    padding:3px 12px 3px 4px; margin-left:2px;
    border-radius:999px; background:var(--panel); border:1px solid var(--line);
    color:var(--fg); font-size:12px; font-weight:500;
    transition:border-color var(--transition), background var(--transition);
  }
  .user-chip:hover { border-color:color-mix(in srgb, var(--line) 55%, var(--accent)); }
  .user-chip .avatar {
    width:26px; height:26px; border-radius:50%;
    background:linear-gradient(135deg, var(--eda-blue-500), var(--eda-teal-400));
    color:#fff; font-size:11px; font-weight:700;
    display:flex; align-items:center; justify-content:center;
    text-transform:uppercase; letter-spacing:.02em;
    box-shadow:0 0 0 2px var(--accent-soft);
  }
  @media (max-width:560px){ .user-chip .uname { display:none; } }

  /* Theme toggle — EDA icon button (cable-map parity) */
  .theme-btn {
    width:32px; height:32px; padding:0; border:0; border-radius:var(--radius-sm);
    background:transparent; color:var(--muted); cursor:pointer;
    display:inline-flex; align-items:center; justify-content:center;
    transition:background var(--transition), color var(--transition);
  }
  .theme-btn:hover { background:var(--state); color:var(--fg); }
  .theme-btn:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .theme-btn svg { width:18px; height:18px; display:block; }
  .theme-btn .icon-sun { display:none; }
  html[data-theme="dark"] .theme-btn .icon-moon { display:none; }
  html[data-theme="dark"] .theme-btn .icon-sun { display:block; }

  /* Buttons */
  .btn {
    border:0; border-radius:var(--radius-sm); padding:9px 16px; font:600 13px/1 inherit;
    letter-spacing:.01em; cursor:pointer; display:inline-flex; align-items:center; gap:8px;
    text-decoration:none; transition:background var(--transition), box-shadow var(--transition), transform .08s;
  }
  .btn:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .btn.contained { background:var(--accent); color:#fff; box-shadow:var(--shadow-sm); }
  .btn.contained:hover { background:var(--accent2); box-shadow:var(--shadow-md); }
  .btn.contained:active { transform:translateY(1px); }
  .btn.contained:disabled { background:var(--neutral-bd); color:#fff; box-shadow:none; cursor:not-allowed; }
  .btn.text { background:transparent; color:var(--accent); padding:9px 12px; }
  .btn.text:hover { background:var(--state); }
  .btn.text.subtle { color:var(--muted); }
  .btn.text.subtle:hover { color:var(--fg); background:var(--state); }
  .btn.text.danger { color:var(--err-fg); }
  .btn.text.danger:hover { background:var(--err-bg); }
  .btn.text.danger:disabled { color:var(--muted); background:transparent; cursor:not-allowed; opacity:.55; }

  /* Layout */
  .app-shell { max-width:1240px; margin:0 auto; padding:20px 20px 56px; }
  .page-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px;
    margin:0 0 20px; flex-wrap:wrap; padding:18px 20px; border-radius:var(--radius-lg);
    border:1px solid var(--line); background:linear-gradient(135deg,
      color-mix(in srgb, var(--panel) 92%, var(--accent) 8%),
      color-mix(in srgb, var(--panel) 96%, var(--surface) 4%));
    box-shadow:var(--shadow-sm); }
  .page-title { margin:0; font-size:22px; font-weight:600; letter-spacing:-.01em;
    display:flex; align-items:center; gap:10px; }
  .page-sub { margin:6px 0 0; color:var(--muted); font-size:13px; max-width:640px; line-height:1.5; }
  .count {
    display:inline-flex; align-items:center; justify-content:center; min-width:20px; height:20px;
    padding:0 6px; font-size:11px; font-weight:700; color:#fff; background:var(--accent);
    border-radius:999px; transition:transform var(--transition);
  }
  .count.pop { animation:badgePop .35s ease; }

  /* Cards */
  .card {
    background:var(--panel); border:1px solid var(--line); border-radius:var(--radius-lg);
    margin-bottom:16px; overflow:hidden; box-shadow:var(--shadow-sm);
    transition:border-color var(--transition), box-shadow var(--transition);
  }
  .card:hover { border-color:color-mix(in srgb,var(--line) 70%, var(--accent)); }
  .card-header {
    display:flex; align-items:center; justify-content:space-between; gap:12px;
    padding:14px 18px; border-bottom:1px solid var(--line); background:color-mix(in srgb,var(--panel) 88%, var(--surface));
  }
  .card-header .section-title { margin:0; font-size:14px; font-weight:600; }
  .card-header .card-hint { font-size:12px; color:var(--muted); }
  .form-card { padding:0; }
  .form-card .card-body { padding:18px 20px 20px; }
  .section-title { margin:0 0 14px; font-size: 16px; font-weight:600; }

  /* Storage */
  .storage-card { padding:16px 18px; }
  .storage-row { display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-bottom:10px; }
  .storage-label { font-size:11px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.08em; }
  .storage-stat { font-size:13px; color:var(--muted); }
  .storage-stat .mono { color:var(--fg); font-weight:600; }
  .storage-track { height:8px; border-radius:999px; background:var(--panel2); border:1px solid var(--line); overflow:hidden; }
  .storage-fill {
    height:100%; width:0; border-radius:999px;
    background:linear-gradient(90deg,var(--accent),var(--eda-teal-400));
    transition:width .45s ease, background .3s;
  }
  .storage-fill.warn { background:linear-gradient(90deg,var(--eda-yellow-500),var(--eda-yellow-400)); }
  .storage-fill.crit { background:linear-gradient(90deg,var(--eda-red-500),var(--danger-strong)); }

  /* Tables */
  .table-wrap { overflow-x:auto; }
  table.mtable { width:100%; border-collapse:collapse; font-size:13px; }
  .mtable th, .mtable td { text-align:left; padding:11px 16px; border-bottom:1px solid var(--line); vertical-align:top; }
  .mtable thead th {
    color:var(--muted); font-weight:600; font-size:11px; text-transform:uppercase;
    letter-spacing:.06em; white-space:nowrap; background:var(--panel2);
  }
  .mtable th.sortable { cursor:pointer; user-select:none; transition:color var(--transition); }
  .mtable th.sortable:hover { color:var(--fg); }
  .mtable th.sortable .arr { opacity:0; margin-left:5px; font-size:10px; transition:opacity var(--transition); }
  .mtable th.sortable:hover .arr { opacity:.45; }
  .mtable th.sorted { color:var(--accent); }
  .mtable th.sorted .arr { opacity:1; color:var(--accent); }
  .mtable th.num, .mtable td.num { text-align:right; }
  .mtable tbody tr { transition:background var(--transition); }
  .mtable tbody tr:nth-child(even) { background:var(--row-stripe); }
  .mtable tbody tr:hover { background:var(--row-hover); }
  .mtable tbody tr:last-child td { border-bottom:0; }
  td.mono, .mono { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12px; }
  .namecell { font-weight:600; }

  /* Status chips */
  .chip {
    display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:999px;
    font-size:11px; font-weight:600; border:1px solid transparent; white-space:nowrap;
    letter-spacing:.02em;
  }
  .chip::before { content:""; width:6px; height:6px; border-radius:50%; background:currentColor; flex:none; }
  .c-Available, .c-Ready { background:var(--ok-bg); color:var(--ok-fg); border-color:var(--ok-bd); }
  .c-InProgress { background:var(--info-bg); color:var(--info-fg); border-color:var(--info-bd); }
  .c-Error, .c-Failed { background:var(--err-bg); color:var(--err-fg); border-color:var(--err-bd); }
  .c-NoArtifact, .c-empty { background:var(--neutral-bg); color:var(--neutral-fg); border-color:var(--neutral-bd); }
  .c-Uploading, .c-Unzipping, .c-Processing, .c-Pending {
    background:var(--info-bg); color:var(--info-fg); border-color:var(--info-bd);
  }
  .c-Uploading::before, .c-Unzipping::before, .c-Processing::before, .c-Pending::before {
    animation:pulse 1.1s ease-in-out infinite;
  }
  .upinfo { margin-top:6px; font:11px ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--muted); }
  .uprog { margin-top:6px; height:4px; width:180px; max-width:100%; background:var(--panel2);
    border-radius:999px; overflow:hidden; border:1px solid var(--line); }
  .uprog > div { height:100%; background:linear-gradient(90deg,var(--accent),var(--eda-teal-400));
    border-radius:999px; transition:width .15s; }
  .uprog.indet > div { width:40%; animation:indet 1.15s ease-in-out infinite; }
  .reason { color:var(--err-fg); font-size:12px; margin-top:5px; }
  .empty { color:var(--muted); padding:32px 16px; text-align:center; font-size:13px; }

  pre.snippet {
    margin:0; padding:10px 12px; background:var(--panel2); border:1px solid var(--line);
    border-radius:var(--radius-sm); font:12px ui-monospace,SFMono-Regular,Menlo,monospace;
    white-space:pre; overflow-x:auto; color:var(--fg);
  }
  .pending { color:var(--muted); }
  .iconbtn {
    background:var(--panel2); border:1px solid var(--line); color:var(--fg);
    border-radius:var(--radius-sm); padding:5px 12px; font-size:11.5px; font-weight:600;
    cursor:pointer; transition:background var(--transition),border-color var(--transition),color var(--transition),transform .08s;
  }
  .iconbtn:hover { border-color:var(--accent); color:var(--accent); }
  .iconbtn.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
  .iconbtn.primary:hover { background:var(--accent2); border-color:var(--accent2); color:#fff; }
  .iconbtn.del { background:var(--danger); border-color:var(--danger); color:var(--on-danger); }
  .iconbtn.del:hover { background:var(--danger-strong); border-color:var(--danger-strong); }
  .iconbtn + .iconbtn { margin-left:8px; }
  .copybtn { background:var(--accent-soft); border-color:var(--accent); color:var(--accent); }
  .copybtn:hover { background:var(--accent); border-color:var(--accent); color:#fff; }

  /* Dialogs */
  .scrim { position:fixed; inset:0; background:var(--scrim); opacity:0; visibility:hidden;
    transition:opacity .2s; z-index:40; backdrop-filter:blur(2px); }
  .scrim.show { opacity:1; visibility:visible; }
  .dialog {
    position:fixed; z-index:50; left:50%; top:50%;
    transform:translate(-50%,-48%) scale(.97); opacity:0; visibility:hidden;
    width:min(560px,calc(100vw - 32px)); max-height:calc(100vh - 48px); overflow:auto;
    background:var(--panel); border:1px solid var(--line); border-radius:var(--radius-lg);
    box-shadow:var(--shadow-lg); transition:opacity .2s, transform .2s;
  }
  .dialog.open { transform:translate(-50%,-50%) scale(1); opacity:1; visibility:visible; }
  .dialog.confirm { width:min(420px,calc(100vw - 32px)); }
  .dialog.wide { width:min(780px,calc(100vw - 32px)); }
  .np-sec { margin-top:14px; }
  .np-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; }
  .np-label { font-size:12px; font-weight:600; color:var(--muted); }
  .dialog .snippet { max-height:46vh; overflow:auto; }
  .dialog-title { margin:0; padding:20px 22px 6px; font-size:17px; font-weight:600; }
  .dialog-body { padding:8px 22px 4px; }
  .dialog-body p { margin:6px 0 4px; color:var(--muted); font-size:13px; line-height:1.5; }
  .dialog-actions { display:flex; justify-content:flex-end; gap:8px; padding:14px 18px 18px; border-top:1px solid var(--line); margin-top:8px; }
  .dialog-title.danger-title { color:var(--err-fg); }
  .warn-list { margin:10px 0 4px; padding-left:18px; color:var(--muted); font-size:13px; line-height:1.5; }
  .warn-list li { margin:3px 0; }
  .warn-list li b, .warn-list li .mono { color:var(--fg); }
  label.ack {
    display:flex; align-items:flex-start; gap:9px; margin:14px 0 2px; padding:10px 12px;
    background:var(--err-bg); border:1px solid var(--err-bd); border-radius:var(--radius-md);
    font-size:12.5px; color:var(--fg); cursor:pointer;
  }
  label.ack input { margin-top:1px; accent-color:var(--err-fg); flex:none; }

  /* Form fields */
  .tf { position:relative; margin-top:16px; }
  .tf input, .tf textarea, .tf select {
    width:100%; padding:13px 12px; border:1px solid var(--line); border-radius:var(--radius-sm);
    background:var(--input-bg); color:var(--fg); font:14px inherit;
    transition:border-color var(--transition), box-shadow var(--transition);
  }
  .tf input:focus, .tf textarea:focus, .tf select:focus {
    outline:none; border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft);
  }
  .tf input:disabled, .tf textarea:disabled { opacity:.55; cursor:not-allowed; }
  .tf label {
    position:absolute; left:9px; top:13px; padding:0 5px; background:var(--panel);
    color:var(--muted); font-size:14px; pointer-events:none; transition:.14s ease;
  }
  .tf input:focus ~ label, .tf input:not(:placeholder-shown) ~ label,
  .tf textarea:focus ~ label, .tf textarea:not(:placeholder-shown) ~ label { top:-8px; font-size:11.5px; }
  .tf input:focus ~ label, .tf textarea:focus ~ label { color:var(--accent); }
  .tf textarea {
    font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    resize:vertical; min-height:80px;
  }
  .tf.select select { padding-right:38px; appearance:none; -webkit-appearance:none; cursor:pointer; }
  .tf.select select:required:invalid { color:var(--muted); }
  .tf.select select option { color:var(--fg); background:var(--panel); }
  .tf.select label { top:-8px; font-size:11.5px; }
  .tf.select::after {
    content:""; position:absolute; right:15px; top:20px; width:8px; height:8px;
    border-right:2px solid var(--muted); border-bottom:2px solid var(--muted);
    transform:rotate(45deg); pointer-events:none;
  }
  .helper { margin:6px 4px 0; font-size:11.5px; color:var(--muted); line-height:1.45; }

  .filefield { margin-top:4px; }
  .filefield > .lbl { font-size:12px; color:var(--muted); font-weight:600; }
  .filebox {
    margin-top:8px; display:flex; align-items:center; gap:12px; flex-wrap:wrap;
    border:1px dashed var(--line-soft); border-radius:var(--radius-md); padding:14px;
    background:var(--panel2); transition:border-color var(--transition), background var(--transition);
  }
  .filebox:hover, .filebox:focus-within { border-color:var(--accent); background:var(--state); }
  .filebox input[type=file] { color:var(--muted); font-size:12.5px; max-width:100%; }
  .filebox input[type=file]::file-selector-button {
    background:var(--accent); color:#fff; border:0; border-radius:var(--radius-sm);
    padding:8px 14px; margin-right:12px; cursor:pointer; font-weight:600; font-size:12.5px;
    transition:background var(--transition);
  }
  .filebox input[type=file]::file-selector-button:hover { background:var(--accent2); }

  /* Snackbar */
  .snackbar {
    position:fixed; left:50%; bottom:24px; transform:translate(-50%,140%);
    z-index:60; min-width:300px; max-width:min(560px,calc(100vw - 32px));
    background:var(--snack-bg); color:var(--snack-fg); border:1px solid var(--line);
    border-radius:var(--radius-md); box-shadow:var(--shadow-lg);
    padding:12px 12px 12px 16px; display:flex; align-items:center; gap:12px;
    opacity:0; visibility:hidden; transition:transform .26s cubic-bezier(.2,.7,.3,1), opacity .26s;
  }
  .snackbar.show { transform:translate(-50%,0); opacity:1; visibility:visible; }
  .snackbar .stext { flex:1; font-size:13px; line-height:1.45; word-break:break-word; }
  .snackbar .sdot { width:8px; height:8px; border-radius:50%; flex:none; }
  .snackbar.ok .sdot { background:var(--eda-green-500); }
  .snackbar.err .sdot { background:var(--eda-red-500); }
  .snackbar .saction {
    background:transparent; border:0; color:var(--snack-action);
    font:600 12px inherit; letter-spacing:.04em; text-transform:uppercase; cursor:pointer;
    padding:6px 10px; border-radius:var(--radius-sm);
  }
  .snackbar .saction:hover { background:var(--state); }

  /* Embedded mode */
  html.eda-embedded .appbar { display:none; }
  html.eda-embedded .app-shell { max-width:none; padding:16px 18px 40px; min-height:60vh; }
  html.eda-embedded .page-head { margin-top:0; }
  html.eda-embedded .theme-btn { display:none; }
  html.eda-embedded .live-pill { display:none; }
  #boot-shell { padding:12px 4px 8px; color:var(--muted); font-size:13px; }
  #boot-shell.hide { display:none; }
  .auth-banner {
    display:none; margin:0 0 14px; padding:10px 14px; border-radius:var(--radius-md);
    background:var(--info-bg); color:var(--info-fg); border:1px solid var(--info-bd);
    font-size:13px; line-height:1.45;
  }
  .auth-banner.show { display:block; }
  .auth-banner.err { background:var(--err-bg); color:var(--err-fg); border-color:var(--err-bd); }

  /* Tabs — EDA-style segmented bar */
  .tabs {
    display:flex; gap:2px; margin:0 0 16px; padding:4px;
    background:var(--panel); border:1px solid var(--line); border-radius:var(--radius-md);
    overflow-x:auto; scrollbar-width:none;
  }
  .tabs::-webkit-scrollbar { display:none; }
  .tab {
    background:transparent; border:0; border-radius:var(--radius-sm);
    color:var(--muted); cursor:pointer; font:600 13px inherit; padding:9px 16px;
    white-space:nowrap; transition:background var(--transition), color var(--transition), box-shadow var(--transition);
    flex:1 1 auto; text-align:center; min-width:max-content;
  }
  .tab:hover { color:var(--fg); background:var(--state); }
  .tab.active {
    color:#fff; background:var(--accent);
    box-shadow:0 2px 8px rgba(0,90,255,.35); border:1px solid transparent;
  }
  .tab-panel {
    display:none; opacity:0; transform:translateY(4px);
    transition:opacity .22s ease, transform .22s ease;
  }
  .tab-panel.active { display:block; opacity:1; transform:none; animation:fadeIn .28s ease; }
  .form-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:18px; padding-top:4px; }
  .status-meta { font-size:12.5px; color:var(--muted); margin:0 0 14px; line-height:1.5; }
  .status-meta .mono { color:var(--fg); }
  .status-grid { display:grid; gap:16px; }
  @media (min-width:900px){ .status-grid { grid-template-columns:1fr; } }

  /* KPI overview cards (dashboard-first, cable-map style) */
  .kpi-grid {
    display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px; margin-bottom:16px;
  }
  @media (max-width:760px){ .kpi-grid { grid-template-columns:repeat(2, minmax(0,1fr)); } }
  .kpi-card {
    display:flex; align-items:center; gap:12px; padding:14px 16px;
    background:var(--panel); border:1px solid var(--line); border-radius:var(--radius-lg);
    box-shadow:var(--shadow-sm); transition:border-color var(--transition), transform var(--transition);
  }
  .kpi-card:hover { border-color:color-mix(in srgb,var(--line) 60%, var(--accent)); transform:translateY(-1px); }
  .kpi-icon {
    width:38px; height:38px; flex:none; border-radius:10px;
    display:flex; align-items:center; justify-content:center;
  }
  .kpi-icon svg { width:19px; height:19px; display:block; }
  .kpi-icon.total { background:var(--accent-soft); color:var(--accent2); }
  .kpi-icon.ok { background:var(--ok-bg); color:var(--ok-fg); }
  .kpi-icon.info { background:var(--info-bg); color:var(--info-fg); }
  .kpi-icon.err { background:var(--err-bg); color:var(--err-fg); }
  .kpi-val { font-size:21px; font-weight:700; line-height:1.15; letter-spacing:-.01em;
    font-variant-numeric:tabular-nums; transition:color var(--transition); }
  .kpi-label { font-size:11px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.07em; }
  .kpi-val.bump { animation:badgePop .35s ease; }

  /* Platform ops strip (controller / storage / reconcile) */
  .ops-grid {
    display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:12px; margin-bottom:12px;
  }
  @media (max-width:900px){ .ops-grid { grid-template-columns:1fr; } }
  .ops-card {
    padding:14px 16px; background:var(--panel); border:1px solid var(--line);
    border-radius:var(--radius-lg); box-shadow:var(--shadow-sm);
    transition:border-color var(--transition), transform var(--transition);
  }
  .ops-card:hover { border-color:color-mix(in srgb,var(--line) 55%, var(--accent)); }
  .ops-head { display:flex; align-items:center; gap:8px; font-size:11px; font-weight:700;
    color:var(--muted); text-transform:uppercase; letter-spacing:.08em; margin-bottom:8px; }
  .ops-icon { width:28px; height:28px; border-radius:8px; display:flex; align-items:center;
    justify-content:center; flex:none; }
  .ops-icon svg { width:15px; height:15px; display:block; }
  .ops-icon.ctrl { background:var(--accent-soft); color:var(--accent2); }
  .ops-icon.store { background:var(--info-bg); color:var(--info-fg); }
  .ops-icon.sync { background:var(--ok-bg); color:var(--ok-fg); }
  .ops-val { font-size:17px; font-weight:700; letter-spacing:-.01em; line-height:1.2; }
  .ops-sub { margin-top:4px; font-size:12px; color:var(--muted); line-height:1.45; }
  .ops-alert {
    display:none; margin-bottom:14px; padding:12px 14px; border-radius:var(--radius-md);
    border:1px solid var(--warn-bd); background:var(--warn-bg); color:var(--warn-fg);
    font-size:12.5px; line-height:1.5;
  }
  .ops-alert span { display:block; }
  .ops-alert span + span { margin-top:4px; }
  .ha-panel { margin-top:16px; padding:14px 16px; border-radius:var(--radius-md);
    border:1px dashed var(--line); background:color-mix(in srgb, var(--panel) 90%, var(--surface)); }
  .ha-panel h3 { margin:0 0 8px; font-size:13px; font-weight:600; }
  .ha-panel p, .ha-panel li { margin:0 0 8px; font-size:12.5px; color:var(--muted); line-height:1.55; }
  .ha-panel ul { margin:0; padding-left:18px; }
  .ha-badge { display:inline-flex; align-items:center; gap:6px; padding:2px 8px; border-radius:999px;
    font-size:10px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
    background:var(--neutral-bg); color:var(--neutral-fg); border:1px solid var(--neutral-bd); }

  .empty .btn { margin-top:10px; }
  .imports-table { padding:0; }
  .imports-table .card-body { padding:14px 18px 18px; }
  .imports-table h3 { margin:0 0 10px; font-size:13px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }
  .chk-row { display:flex; align-items:center; gap:9px; margin-top:14px; font-size:13px; color:var(--muted); }
  .chk-row input { accent-color:var(--accent); }

  @media (max-width:640px){
    .app-shell { padding:14px 14px 40px; }
    .mtable th, .mtable td { padding:10px 12px; }
    .form-actions { flex-direction:column; align-items:stretch; }
    .form-actions .btn { width:100%; justify-content:center; }
  }
</style>
<script>try{var _e=window.self!==window.top;if(_e)document.documentElement.classList.add("eda-embedded");var _t=localStorage.getItem("imagemanager-theme")||"dark";document.documentElement.setAttribute("data-theme",_t);}catch(e){}</script>
</head>
<body>
<noscript><div style="padding:24px 20px;background:#121c2a;color:#e6edf3;font:14px sans-serif">
  Image Manager requires JavaScript. Enable it, or open
  <a href="/core/httpproxy/v1/imagemanager/" style="color:#4d8dff">/core/httpproxy/v1/imagemanager/</a>
  in a new tab.</div></noscript>
<header class="appbar">
  <div class="brand">
    <span class="brand-logo" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 3l8 4.4-8 4.4-8-4.4L12 3z" fill="#fff" opacity=".95"/>
        <path d="M4.4 12.6L12 16.8l7.6-4.2" stroke="#fff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" opacity=".72"/>
        <path d="M4.4 16.6L12 20.8l7.6-4.2" stroke="#fff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" opacity=".42"/>
      </svg>
    </span>
    <div class="brand-text">
      <span class="brand-row">
        <span class="brand-name">Image Manager</span>
        <span id="verBadge" class="ver-badge" style="display:none" title="App version"></span>
      </span>
      <span class="brand-sub">Vendor NOS images for EDA bootstrap &amp; Digital Twin</span>
    </div>
  </div>
  <div class="appbar-actions">
    <span id="liveIndicator" class="live-pill" title="Status polling active on the Status tab">
      <span class="live-dot" aria-hidden="true"></span><span class="live-label">Live</span>
    </span>
    <span id="userInfo" class="user-chip" style="display:none"><span class="avatar" id="avatar"></span><span class="uname" id="uname"></span></span>
    <button type="button" id="themeBtn" class="theme-btn" title="Toggle light / dark appearance" aria-label="Toggle theme">
      <svg class="icon-moon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.5 5.5 0 0 1-4.4 2.26 5.5 5.5 0 0 1-5.45-6.19A9 9 0 0 0 12 3z"/></svg>
      <svg class="icon-sun" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zm0-5h2v3h-2V2zm0 17h2v3h-2v-3zM4.22 4.22l1.42 1.42L4.22 7.06 2.8 5.64 4.22 4.22zm15.56 0 1.42 1.42-1.42 1.42-1.42-1.42 1.42-1.42zM2 12h3v2H2v-2zm17 0h3v2h-3v-2zm-2.8 6.36 1.42 1.42 1.42-1.42-1.42-1.42-1.42 1.42zM4.22 19.78l1.42-1.42 1.42 1.42-1.42 1.42-1.42-1.42z"/></svg>
    </button>
    <a id="signoutLink" class="btn text subtle ripple" title="Sign out of Image Manager">Sign out</a>
  </div>
</header>

<main class="app-shell">
  <div id="boot-shell" role="status">Loading Image Manager&hellip;</div>
  <div id="authBanner" class="auth-banner" role="status" aria-live="polite"></div>
  <header class="page-head">
    <div>
      <h1 class="page-title">Image Manager</h1>
      <p class="page-sub">Upload vendor NOS images, import by URL, and track Artifact download status — served to EDA for ZTP, upgrades and Digital Twin.</p>
    </div>
  </header>

  <nav class="tabs" role="tablist" aria-label="Image Manager sections">
    <button type="button" class="tab active ripple" id="tab-status" data-tab="status" role="tab" aria-selected="true" aria-controls="panel-status">Dashboard <span class="count" id="statusCount" style="display:none"></span></button>
    <button type="button" class="tab ripple" id="tab-upload" data-tab="upload" role="tab" aria-controls="panel-upload">Upload</button>
    <button type="button" class="tab ripple" id="tab-url-import" data-tab="url-import" role="tab" aria-controls="panel-url-import">URL Import</button>
    <button type="button" class="tab ripple" id="tab-settings" data-tab="settings" role="tab" aria-controls="panel-settings">Settings</button>
  </nav>

  <!-- Upload tab -->
  <section id="panel-upload" class="tab-panel" role="tabpanel" aria-labelledby="tab-upload">
    <div class="card form-card">
      <div class="card-header"><h2 class="section-title">Upload image from file</h2><span class="card-hint">Vendor .zip</span></div>
      <div class="card-body">
      <div class="filefield">
        <span class="lbl">Vendor image &mdash; <span class="mono">.zip</span> (required)</span>
        <div class="filebox">
          <input type="file" id="binFile" accept=".zip">
        </div>
        <div class="helper" id="binHint"></div>
      </div>
      <div class="tf select">
        <select id="namespace" required>
          <option value="" disabled selected>Select a namespace&hellip;</option>
        </select>
        <label for="namespace">Namespace</label>
        <div class="helper">Choose the EDA namespace where the Artifact(s) will be created.</div>
      </div>
      <div class="tf">
        <input type="text" id="imageName" placeholder=" " autocomplete="off">
        <label for="imageName">Image name (auto-generated &mdash; edit if you like)</label>
        <div class="helper" id="nameHint">SR Linux, SR OS (7750 TiMOS) or SR-SIM is detected automatically from the zip.</div>
      </div>
      <div class="tf">
        <textarea id="licText" placeholder=" " rows="3" spellcheck="false" autocapitalize="off" autocomplete="off"></textarea>
        <label for="licText">License key (optional)</label>
        <div class="helper" id="licHint">Paste the SR OS / SR Linux simulator license key if needed.</div>
      </div>
      <div class="form-actions">
        <button class="btn contained ripple" id="uploadBtn">Upload &amp; create Artifact</button>
      </div>
      </div>
    </div>
  </section>

  <!-- URL Import tab -->
  <section id="panel-url-import" class="tab-panel" role="tabpanel" aria-labelledby="tab-url-import">
    <div class="card form-card">
      <div class="card-header"><h2 class="section-title">Import image from URL</h2><span class="card-hint">Remote download</span></div>
      <div class="card-body">
      <p class="status-meta">The controller downloads the vendor <span class="mono">.zip</span> from your URL and creates the same Artifact(s) as a file upload.</p>
      <div class="tf">
        <input type="url" id="urlSource" placeholder=" " autocomplete="off">
        <label for="urlSource">Source URL (http or https)</label>
      </div>
      <div class="tf select">
        <select id="urlNamespace" required>
          <option value="" disabled selected>Select a namespace&hellip;</option>
        </select>
        <label for="urlNamespace">Namespace</label>
      </div>
      <div class="tf">
        <input type="text" id="urlName" placeholder=" " autocomplete="off">
        <label for="urlName">Name override (optional)</label>
      </div>
      <div class="tf">
        <textarea id="urlLicText" placeholder=" " rows="3" spellcheck="false" autocapitalize="off" autocomplete="off"></textarea>
        <label for="urlLicText">License key (optional)</label>
      </div>
      <label class="chk-row"><input type="checkbox" id="urlInsecure"> Skip TLS certificate verification on source URL (lab only)</label>
      <div class="form-actions">
        <button class="btn contained ripple" id="urlImportBtn">Start URL import</button>
      </div>
      </div>
    </div>
  </section>

  <!-- Settings tab -->
  <section id="panel-settings" class="tab-panel" role="tabpanel" aria-labelledby="tab-settings">
    <div class="card form-card">
      <div class="card-header"><h2 class="section-title">Image Manager settings</h2><span class="card-hint">Controller config</span></div>
      <div class="card-body">
      <p class="status-meta" id="settingsMeta">&mdash;</p>
      <div class="tf">
        <input type="text" id="setDefaultNs" placeholder=" " autocomplete="off">
        <label for="setDefaultNs">Default artifact namespace</label>
      </div>
      <div class="tf">
        <input type="text" id="setDefaultRepo" placeholder=" " autocomplete="off">
        <label for="setDefaultRepo">Default repo</label>
      </div>
      <div class="tf">
        <input type="number" id="setMaxMiB" placeholder=" " min="1" max="65536" step="1">
        <label for="setMaxMiB">Max upload size (MiB)</label>
      </div>
      <div class="tf">
        <input type="text" id="setPullBase" placeholder=" " autocomplete="off">
        <label for="setPullBase">File-pull base URL (advanced, optional)</label>
        <div class="helper">Leave empty to auto-derive from the in-cluster Service.</div>
      </div>
      <div class="form-actions">
        <button class="btn text subtle ripple" id="settingsReload">Reload</button>
        <button class="btn contained ripple" id="settingsSave">Save settings</button>
      </div>
      <div class="ha-panel" id="haPanel">
        <h3>High availability &amp; storage <span class="ha-badge">Lab-friendly</span></h3>
        <p>Image Manager runs as a <strong>single-replica</strong> controller with a <strong>ReadWriteOnce PVC</strong>. This is ideal for lab and pilot deployments; the controller re-derives upload state from the PVC and Artifact CRs on every startup.</p>
        <ul>
          <li><strong>PVC backup:</strong> back up the <span class="mono">imagemanager-data</span> volume periodically — it is the durable origin eda-asvr re-pulls from.</li>
          <li><strong>External origin:</strong> set <em>File-pull base URL</em> above to point Artifact CRs at an existing HTTPS artifact store (S3-compatible gateway, Artifactory, etc.) instead of this pod.</li>
          <li><strong>Node agent:</strong> the DaemonSet re-resolves the in-cluster registry redirect every cycle — no cached ClusterIP assumptions.</li>
        </ul>
      </div>
      </div>
    </div>
  </section>

  <!-- Status tab (Dashboard — start screen) -->
  <section id="panel-status" class="tab-panel active" role="tabpanel" aria-labelledby="tab-status">
    <div class="kpi-grid" aria-label="Overview">
      <div class="kpi-card">
        <span class="kpi-icon total" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none"><path d="M12 3l8 4.4-8 4.4-8-4.4L12 3z" fill="currentColor"/><path d="M4.4 12.6L12 16.8l7.6-4.2M4.4 16.6L12 20.8l7.6-4.2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" opacity=".6"/></svg>
        </span>
        <div><div class="kpi-val" id="kpiTotal">&mdash;</div><div class="kpi-label">Images</div></div>
      </div>
      <div class="kpi-card">
        <span class="kpi-icon ok" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none"><path d="M20 6.5L9.5 17 4 11.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </span>
        <div><div class="kpi-val" id="kpiReady">&mdash;</div><div class="kpi-label">Available</div></div>
      </div>
      <div class="kpi-card">
        <span class="kpi-icon info" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none"><path d="M12 4v4m0 8v4M4 12h4m8 0h4M6.3 6.3l2.85 2.85m5.7 5.7l2.85 2.85M6.3 17.7l2.85-2.85m5.7-5.7l2.85-2.85" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>
        </span>
        <div><div class="kpi-val" id="kpiActive">&mdash;</div><div class="kpi-label">In progress</div></div>
      </div>
      <div class="kpi-card">
        <span class="kpi-icon err" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none"><path d="M12 8v5m0 3.4v.1M10.3 4l-8 14a2 2 0 001.7 3h16a2 2 0 001.7-3l-8-14a2 2 0 00-3.4 0z" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </span>
        <div><div class="kpi-val" id="kpiFailed">&mdash;</div><div class="kpi-label">Failed</div></div>
      </div>
    </div>
    <div class="ops-grid" aria-label="Platform status">
      <div class="ops-card">
        <div class="ops-head">
          <span class="ops-icon ctrl" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><rect x="4" y="5" width="16" height="6" rx="1.5" stroke="currentColor" stroke-width="1.8"/><rect x="4" y="13" width="16" height="6" rx="1.5" stroke="currentColor" stroke-width="1.8"/></svg></span>
          Controller
        </div>
        <div class="ops-val" id="opsHealth">&mdash;</div>
        <div class="ops-sub" id="opsHealthMsg">Single-replica deployment</div>
      </div>
      <div class="ops-card">
        <div class="ops-head">
          <span class="ops-icon store" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><ellipse cx="12" cy="6" rx="7" ry="3" stroke="currentColor" stroke-width="1.8"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" stroke="currentColor" stroke-width="1.8"/></svg></span>
          Storage
        </div>
        <div class="ops-val" id="opsStorageMode">PVC</div>
        <div class="ops-sub" id="opsStorageSub">RWO volume &mdash; durable origin for eda-asvr</div>
      </div>
      <div class="ops-card">
        <div class="ops-head">
          <span class="ops-icon sync" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M4 12a8 8 0 0113.7-5.7M20 12a8 8 0 01-13.7 5.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M20 4v4h-4M4 20v-4h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
          Reconcile
        </div>
        <div class="ops-val" id="opsReconcile">&mdash;</div>
        <div class="ops-sub" id="opsReconcileSub">Re-derives PVC vs Artifact state on startup</div>
      </div>
    </div>
    <div id="opsAlert" class="ops-alert" style="display:none" role="status" aria-live="polite"></div>
    <div class="status-grid">
    <div class="card storage-card">
      <div class="storage-row">
        <span class="storage-label">App storage</span>
        <span class="storage-stat" id="storageStat">&mdash;</span>
      </div>
      <div class="storage-track"><div class="storage-fill" id="storageFill"></div></div>
    </div>
    <div class="card">
      <div class="card-header"><h2 class="section-title">Artifacts</h2>
        <span style="display:inline-flex;align-items:center;gap:10px">
          <span class="card-hint">Live status</span>
          <button class="iconbtn ripple" id="refreshBtn" title="Refresh now">Refresh</button>
        </span>
      </div>
      <div class="table-wrap">
        <table class="mtable">
          <thead><tr>
            <th class="sortable" data-sort="displayName">Name <span class="arr"></span></th>
            <th class="sortable" data-sort="namespace">Namespace <span class="arr"></span></th>
            <th class="sortable num" data-sort="sizeBytes">Size <span class="arr"></span></th>
            <th class="sortable" data-sort="downloadStatus">Status <span class="arr"></span></th>
            <th></th>
          </tr></thead>
          <tbody id="rows"><tr><td colspan="5" class="empty">Loading&hellip;</td></tr></tbody>
        </table>
      </div>
    </div>
    <div class="card imports-table">
      <div class="card-body">
      <h3>URL imports</h3>
      <div class="table-wrap">
        <table class="mtable">
          <thead><tr>
            <th>Name</th><th>Namespace</th><th>Source URL</th><th>Phase</th><th>Message</th>
          </tr></thead>
          <tbody id="importRows"><tr><td colspan="5" class="empty">Loading&hellip;</td></tr></tbody>
        </table>
      </div>
      </div>
    </div>
    </div>
  </section>
</main>

<!-- scrim shared by all dialogs -->
<div class="scrim" id="scrim"></div>

<!-- upload dialog removed — inline on Upload tab -->

<!-- nodeprofile dialog -->
<div class="dialog wide" id="npDialog" role="dialog" aria-modal="true" aria-labelledby="npTitle">
  <h2 class="dialog-title" id="npTitle">NodeProfile</h2>
  <div class="dialog-body">
    <p id="npIntro">Paste the <b>snippet</b> into an existing <span class="mono">NodeProfile</span>'s <span class="mono">spec.images</span>, or copy the <b>complete example</b> as a starting point. The image path(s), version, OS and <span class="mono">yang</span> are filled from this image; <span class="mono">&lt;…&gt;</span> values are for you to set.</p>
    <div class="np-sec">
      <div class="np-head"><span class="np-label" id="npSnipLabel">Snippet &mdash; <span class="mono">spec.images</span></span><button class="iconbtn copybtn ripple" id="npCopySnip">Copy</button></div>
      <pre class="snippet" id="npSnippet"></pre>
    </div>
    <div class="np-sec">
      <div class="np-head"><span class="np-label">Complete NodeProfile example</span><button class="iconbtn copybtn ripple" id="npCopyFull">Copy</button></div>
      <pre class="snippet" id="npFull"></pre>
    </div>
  </div>
  <div class="dialog-actions">
    <button class="btn text danger ripple" id="npDelete">Delete image</button>
    <button class="btn text subtle ripple" id="npClose">Close</button>
  </div>
</div>

<!-- replace-on-conflict confirm dialog -->
<div class="dialog confirm" id="replaceDialog" role="dialog" aria-modal="true" aria-labelledby="replaceTitle">
  <h2 class="dialog-title" id="replaceTitle">Replace existing artifact?</h2>
  <div class="dialog-body">
    <p id="replaceLead"></p>
    <p class="hint">If the image is already stored locally, Artifact CRs will be recreated from PVC storage (no re-download).</p>
  </div>
  <div class="dialog-actions">
    <button class="btn text subtle ripple" id="replaceCancel">Cancel</button>
    <button class="btn primary ripple" id="replaceOk">Replace</button>
  </div>
</div>

<!-- delete-artifact confirm dialog (warning + explicit acknowledgement) -->
<div class="dialog confirm" id="confirmDialog" role="dialog" aria-modal="true" aria-labelledby="confirmTitle">
  <h2 class="dialog-title danger-title" id="confirmTitle">Delete artifact</h2>
  <div class="dialog-body">
    <p id="confirmLead"></p>
    <ul class="warn-list" id="confirmList"></ul>
    <label class="ack"><input type="checkbox" id="confirmAck"> I understand this permanently removes the artifact and can't be undone.</label>
  </div>
  <div class="dialog-actions">
    <button class="btn text subtle ripple" id="confirmCancel">Cancel</button>
    <button class="btn text danger ripple" id="confirmOk" disabled>Delete artifact</button>
  </div>
</div>

<!-- snackbar -->
<div class="snackbar" id="snackbar">
  <span class="sdot"></span>
  <span class="stext" id="snackText"></span>
  <button class="saction" id="snackClose">Dismiss</button>
</div>

<script>
(function(){
  var API_PROXY_PREFIX = "/core/httpproxy/v1/imagemanager";
  function resolveApiBase(){
    var meta = document.querySelector('meta[name="imagemanager-api-base"]');
    if(meta && meta.content) return meta.content.replace(/\/+$/, "");
    var base = location.pathname.replace(/\/+$/, "");
    if(base && base !== "/" && base.indexOf("imagemanager") >= 0) return base;
    return API_PROXY_PREFIX;
  }
  var apiBase = resolveApiBase();
  function api(p){ return apiBase + p; }
  function fetchJson(url, opts){
    return fetch(url, opts).then(function(r){
      return r.json().then(function(j){ return {ok:r.ok, status:r.status, body:j}; })
        .catch(function(){ return {ok:r.ok, status:r.status, body:null}; });
    });
  }
  var maxBytes = 4096*1024*1024;
  var embedded = window.self !== window.top;
  var authReady = false;
  var SSO_TIMEOUT_MS = 15000;

  function bootDone(){
    var b = document.getElementById("boot-shell");
    if(b) b.classList.add("hide");
  }
  function setAuthBanner(kind, text){
    var b = document.getElementById("authBanner");
    if(!b) return;
    if(!text){ b.className = "auth-banner"; b.textContent = ""; return; }
    b.className = "auth-banner show" + (kind === "err" ? " err" : "");
    b.textContent = text;
  }
  function withTimeout(promise, ms, label){
    return new Promise(function(resolve, reject){
      var done = false;
      var timer = setTimeout(function(){
        if(done) return;
        done = true;
        reject(new Error(label || "timed out"));
      }, ms);
      promise.then(function(v){
        if(done) return;
        done = true; clearTimeout(timer); resolve(v);
      }, function(e){
        if(done) return;
        done = true; clearTimeout(timer); reject(e);
      });
    });
  }

  function loadScript(src){
    return new Promise(function(resolve, reject){
      var s = document.createElement("script");
      s.src = src; s.async = true;
      s.onload = function(){ resolve(); };
      s.onerror = function(){ reject(new Error("script load failed: "+src)); };
      document.head.appendChild(s);
    });
  }
  function exchangeToken(token){
    return fetch(api("/oauth/session"), {
      method: "POST",
      headers: { "Authorization": "Bearer "+token, "Content-Type": "application/json" }
    }).then(function(r){ return r.json().then(function(j){ return {status:r.status, body:j}; }); });
  }
  function silentSso(){
    setAuthBanner("info", "Signing in\u2026");
    return withTimeout(
      loadScript("/core/proxy/v1/identity/js/keycloak.min.js").then(function(){
        if(typeof Keycloak === "undefined") throw new Error("keycloak-js unavailable");
        var kc = new Keycloak({ url: "/core/proxy/v1/identity", realm: "eda", clientId: "auth" });
        return kc.init({
          onLoad: "check-sso",
          silentCheckSsoRedirectUri: location.origin + apiBase + "/oauth/silent-sso.html",
          checkLoginIframe: false
        }).then(function(ok){
          if(ok && kc.token) return exchangeToken(kc.token);
          return null;
        });
      }),
      SSO_TIMEOUT_MS,
      "Sign-in timed out after " + (SSO_TIMEOUT_MS / 1000) + "s"
    ).finally(function(){ setAuthBanner("", ""); });
  }
  function authErrorMessage(ex){
    if(ex && ex.status === 403 && ex.body){
      var roles = (ex.body.allowedRoles || []).join(", ");
      return "Access denied"+(ex.body.user ? (" for "+ex.body.user) : "")+
        (roles ? (": Image Manager requires one of: "+roles+".") : ".");
    }
    if(ex && ex.body && ex.body.error === "not authenticated")
      return "Sign-in required. Reload this page or open Image Manager in a new browser tab.";
    return "Sign-in failed inside EDA. Reload this page or open Image Manager in a new tab.";
  }
  function showFatal(msg){
    bootDone();
    setAuthBanner("err", msg);
    if(rows) rows.innerHTML = '<tr><td colspan="5" class="empty">'+esc(msg)+'</td></tr>';
    snack("err", msg, true);
  }
  function ensureAuth(){
    if(authReady) return Promise.resolve();
    return fetch(api("/api/config")).then(function(r){
      if(r.status === 200){ authReady = true; return r.json(); }
      if(r.status !== 401) throw new Error("config unavailable (HTTP "+r.status+")");
      // Silent SSO first (works in the EDA iframe AND a new tab opened from the
      // dashboard): reuse the browser's existing EDA Keycloak session, no
      // redirect, no re-login. Falls back to the OIDC redirect flow only when
      // silent SSO cannot complete (e.g. keycloak-js unavailable).
      return silentSso().then(function(ex){
        if(ex && ex.status >= 200 && ex.status < 300 && ex.body && ex.body.ok){
          authReady = true;
          return fetch(api("/api/config")).then(function(r2){
            if(r2.status !== 200) throw new Error("config after sso");
            return r2.json();
          });
        }
        if(ex && ex.status === 403){
          var err = new Error("forbidden");
          err.exchange = ex;
          throw err;   // role denied — redirecting would just loop
        }
        if(!embedded){
          window.location = apiBase + "/oauth/login";
          throw new Error("redirect");
        }
        var err2 = new Error("sso failed");
        err2.exchange = ex;
        throw err2;
      }, function(e){
        if(!embedded){
          window.location = apiBase + "/oauth/login";
          throw new Error("redirect");
        }
        throw e;
      });
    });
  }

  var el = function(id){ return document.getElementById(id); };
  var binFile=el("binFile"), ns=el("namespace"), urlNs=el("urlNamespace"),
      imageName=el("imageName"), btn=el("uploadBtn"), binHint=el("binHint"),
      rows=el("rows"), importRows=el("importRows"), licText=el("licText");

  // Lenient structure check: does ANY single line contain a "<node-id> <key>"
  // entry? Surrounding labels / quotes / blank lines don't matter. Tested per-line
  // to mirror the server parser exactly (which iterates lines), so the GUI never
  // accepts a paste the server would then reject.
  function looksLikeLicense(t){
    var RE=/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\s+[A-Za-z0-9+/=]{16,}/;
    return (t||"").split(/\r?\n/).some(function(l){ return RE.test(l); });
  }
  var signout=el("signoutLink"); if(signout) signout.href=apiBase+"/oauth/logout";

  // ---------- tabs ----------
  var activeTab = "status";
  function showTab(name){
    if(name === activeTab) return;
    activeTab = name;
    document.querySelectorAll(".tab").forEach(function(t){
      var on = t.getAttribute("data-tab") === name;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".tab-panel").forEach(function(p){
      var on = p.id === "panel-" + name;
      p.classList.toggle("active", on);
      if(on){ p.style.animation = "none"; void p.offsetWidth; p.style.animation = ""; }
    });
    if(name === "status"){ refresh(); refreshImports(); }
    if(name === "settings"){ loadSettings(); }
    syncLiveIndicator();
  }
  document.querySelectorAll(".tab").forEach(function(t){
    t.addEventListener("click", function(){ showTab(t.getAttribute("data-tab")); });
  });

  // ---------- ripple ----------
  document.body.addEventListener("pointerdown", function(e){
    var t = e.target.closest(".ripple"); if(!t) return;
    if(t.disabled) return;
    var r = t.getBoundingClientRect(), s = Math.max(r.width, r.height);
    var ink = document.createElement("span");
    ink.className = "ripple-ink";
    ink.style.width = ink.style.height = s + "px";
    ink.style.left = (e.clientX - r.left - s/2) + "px";
    ink.style.top = (e.clientY - r.top - s/2) + "px";
    t.appendChild(ink);
    setTimeout(function(){ ink.remove(); }, 560);
  });

  // ---------- helpers ----------
  function fmtBytes(n){
    if(n==null) return "";
    var u=["B","KiB","MiB","GiB","TiB"], i=0; n=Number(n);
    while(n>=1024 && i<u.length-1){ n/=1024; i++; }
    return n.toFixed(i?1:0)+" "+u[i];
  }
  function isZip(name){ return /\.zip$/i.test(name||""); }
  function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(m){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[m]; }); }
  // Suggest a name from the filename; the NOS is detected server-side from the
  // zip contents, so this is just a friendly default the user may edit.
  // Names are always lowercase (Artifact + served path + NodeProfile name), so
  // capitals can never sneak into an EDA object name.
  function deriveName(fn){
    var base=(fn||"").split(/[\\/]/).pop();
    var stem=base.replace(/\.[A-Za-z0-9]+$/,"");
    if(/sr[ _-]?sim/i.test(base)){   // SR-SIM (container image) — distinct from HW SR OS
      var xm=base.match(/(\d+\.\d+\.[Rr]\d+)/)||base.match(/(\d+\.\d+\.\d+(?:-\d+)?)/);
      if(xm) return ("srsim-"+xm[1]).toLowerCase();
    }
    if(/sr[ _-]?linux/i.test(base)){
      var m=base.match(/(\d+\.\d+\.\d+(?:-\d+)?)/);
      if(m) return ("srlinux-"+m[1]).toLowerCase();
    }
    var s=base.match(/(\d+\.\d+\.[Rr]\d+)/);   // SR OS style, e.g. 26.3.R3
    if(s) return ("sros-"+s[1]).toLowerCase();
    return (stem||"image").toLowerCase();
  }

  // ---------- snackbar ----------
  var snackbar=el("snackbar"), snackText=el("snackText"), snackTimer=null;
  function snack(kind, text, sticky){
    snackbar.className = "snackbar show " + (kind==="ok"?"ok":"err");
    snackText.textContent = text;
    if(snackTimer){ clearTimeout(snackTimer); snackTimer=null; }
    if(!sticky){ snackTimer=setTimeout(hideSnack, kind==="ok"?6000:9000); }
  }
  function hideSnack(){ snackbar.classList.remove("show"); }
  el("snackClose").addEventListener("click", hideSnack);

  // ---------- modal infrastructure ----------
  var scrim=el("scrim"), openDlg=null;
  function openModal(d){
    openDlg=d; scrim.classList.add("show"); d.classList.add("open");
    document.body.style.overflow="hidden";
    var f=d.querySelector("input:not([type=file]),button,select,textarea");
    if(f){ try{ f.focus(); }catch(e){} }
  }
  function closeModal(){
    if(openDlg){ openDlg.classList.remove("open"); }
    scrim.classList.remove("show"); document.body.style.overflow=""; openDlg=null;
  }
  scrim.addEventListener("click", closeModal);
  document.addEventListener("keydown", function(e){ if(e.key==="Escape" && openDlg) closeModal(); });

  // ---------- delete-artifact confirm dialog ----------
  // acknowledgement, so deletion is always an informed, explicit action.
  var confirmLead=el("confirmLead"), confirmList=el("confirmList"),
      confirmAck=el("confirmAck"), confirmOk=el("confirmOk"), pendingConfirm=null;
  confirmAck.addEventListener("change", function(){ confirmOk.disabled = !confirmAck.checked; });
  el("confirmCancel").addEventListener("click", closeModal);
  confirmOk.addEventListener("click", function(){
    if(!confirmAck.checked) return;
    var fn=pendingConfirm; pendingConfirm=null; closeModal(); if(fn) fn();
  });
  function askDelete(lead, items, onYes){
    confirmLead.innerHTML = lead;
    confirmList.innerHTML = items.map(function(s){ return "<li>"+s+"</li>"; }).join("");
    confirmAck.checked=false; confirmOk.disabled=true; pendingConfirm=onYes;
    openModal(el("confirmDialog"));
  }

  // ---------- replace-on-conflict confirm dialog ----------
  var replaceLead=el("replaceLead"), replaceOk=el("replaceOk"), pendingReplace=null;
  el("replaceCancel").addEventListener("click", function(){
    pendingReplace=null; closeModal();
  });
  replaceOk.addEventListener("click", function(){
    var fn=pendingReplace; pendingReplace=null; closeModal(); if(fn) fn();
  });
  function askReplace(artifactName, namespace, onReplace){
    replaceLead.innerHTML='Artifact <b class="mono">'+esc(artifactName)+'</b> already exists in '+
      '<span class="mono">'+esc(namespace)+'</span>. Replace it?';
    pendingReplace=onReplace;
    openModal(el("replaceDialog"));
  }
  function isConflictResponse(status, r){
    return status===409 && r && (r.conflict || /already exists/i.test(r.error||""));
  }
  function conflictInfo(r, fallbackName, fallbackNs){
    return {
      artifactName: (r&&r.artifactName)||fallbackName,
      namespace: (r&&r.namespace)||fallbackNs
    };
  }

  function fillNamespaceSelects(names, defaultNs){
    [ns, urlNs].forEach(function(sel){
      if(!sel) return;
      while(sel.options.length > 1) sel.remove(1);
      (names||[]).forEach(function(n){
        var o=document.createElement("option"); o.value=n; o.textContent=n; sel.appendChild(o);
      });
      if(defaultNs){
        for(var i=0;i<sel.options.length;i++){
          if(sel.options[i].value===defaultNs){ sel.selectedIndex=i; break; }
        }
      }
    });
  }

  // ---------- config + namespaces ----------
  bootDone();
  ensureAuth().then(function(c){
    if(c.maxUploadMiB) maxBytes=c.maxUploadMiB*1024*1024;
    binHint.textContent="Maximum upload size: "+(c.maxUploadMiB||Math.round(maxBytes/1048576))+" MiB.";
    if(c.user){
      var ui=el("userInfo"); ui.style.display="inline-flex";
      el("uname").textContent=c.user;
      el("avatar").textContent=(c.user||"?").slice(0,1);
    }
    if(c.version){
      var vb=el("verBadge"); vb.style.display="inline-flex"; vb.textContent=c.version;
    }
    var defaultNs=(c.defaultArtifactNamespace||"").trim();
    fetchJson(api("/api/namespaces")).then(function(res){
      if(res.status===401) return;
      if(!res.ok){
        snack("err","Could not load namespaces (HTTP "+res.status+").", true);
        return;
      }
      fillNamespaceSelects((res.body||{}).namespaces, defaultNs);
    });
    refresh();
    refreshImports();
    syncLiveIndicator();
  }).catch(function(err){
    if(err && err.message === "redirect") return;   // navigating to /oauth/login
    var msg = (err && err.message && err.message.indexOf("timed out") >= 0) ? err.message
            : (err && err.exchange) ? authErrorMessage(err.exchange)
            : (err && err.message && err.message.indexOf("config unavailable")===0) ? err.message
            : authErrorMessage(null);
    showFatal(msg);
  });

  // ---------- file selection ----------
  binFile.addEventListener("change", function(){
    var f=binFile.files[0];
    if(!f) return;
    imageName.value = deriveName(f.name);
    binHint.textContent=f.name+"  ·  "+fmtBytes(f.size);
  });
  // Names are lowercased everywhere; keep the field lowercase as the user edits.
  imageName.addEventListener("input", function(ev){
    if(ev && ev.isComposing) return;   // don't disturb a mid-IME composition
    var s=imageName.selectionStart, e=imageName.selectionEnd, lo=imageName.value.toLowerCase();
    if(lo!==imageName.value){ imageName.value=lo; try{ imageName.setSelectionRange(s,e); }catch(_){} }
  });

  // ---------- upload (closes dialog; progress shown as a live table row) ----------
  function resetUploadForm(){
    binFile.value=""; imageName.value=""; ns.selectedIndex=0; licText.value="";
    binHint.textContent="Maximum upload size: "+Math.round(maxBytes/1048576)+" MiB.";
  }

  // Attach a license to a freshly-uploaded image: POST the raw key file to
  // /api/license. Additive — a failure here never undoes the image upload. baseMsg
  // is the image-upload snack text, folded in so the user sees one coherent result
  // (no green flash that's instantly overwritten).
  function attachLicense(uploadId, what, licStr, baseMsg){
    var pre=baseMsg?(baseMsg+" "):"";
    if(!uploadId || !licStr) { if(baseMsg) snack("ok", baseMsg); refresh(); return; }
    var qs=new URLSearchParams({uploadId:uploadId});
    var xhr=new XMLHttpRequest();
    xhr.open("POST", api("/api/license")+"?"+qs.toString());
    xhr.setRequestHeader("Content-Type","text/plain; charset=utf-8");
    xhr.onload=function(){ var r={}; try{ r=JSON.parse(xhr.responseText); }catch(e){}
      if(xhr.status>=200 && xhr.status<300 && r.ok){
        var warn=r.mismatch?(" Note: that key looks like a "+(r.licenseNos||"different")+
                 " license but the image is "+(r.imageNos||"")+"; using it anyway."):"";
        snack("ok", pre+"License attached."+warn, !!r.mismatch);
      } else {
        snack("err", pre+"But the license could not be attached: "+
              ((r&&r.error)||("HTTP "+xhr.status)), true);
      }
      refresh();
    };
    xhr.onerror=function(){ snack("err", pre+"But attaching the license failed (network).", true); refresh(); };
    xhr.send(licStr);
  }
  function paintPendingCell(p){
    var c=document.getElementById("upstat-"+p.key);
    if(c) c.innerHTML=pendStatusHtml(p); else render();
  }

  // Shared XHR uploader: streams `file` to `url`, driving the live pending row `p`.
  function sendUpload(url, file, p, handlers){
    var xhr=new XMLHttpRequest();
    xhr.open("POST", url);
    var startT=Date.now();
    xhr.upload.onprogress=function(e){
      if(!e.lengthComputable) return;
      p.loaded=e.loaded; p.total=e.total||p.total;
      p.pct=p.total ? (e.loaded/p.total*100) : 0;
      p.elapsed=(Date.now()-startT)/1000;
      p.speed=p.elapsed>0 ? (e.loaded/1048576/p.elapsed) : 0;
      paintPendingCell(p);
    };
    xhr.upload.onload=function(){ if(handlers.onBodySent) handlers.onBodySent(); };
    xhr.onload=function(){ var r={}; try{ r=JSON.parse(xhr.responseText);}catch(e){}
      handlers.onDone(xhr.status, r); };
    xhr.onerror=function(){ handlers.onError(); };
    xhr.send(file);
    return xhr;
  }

  // Single upload path. The NOS is auto-detected server-side from the zip; md5
  // and the YANG schema profile are handled automatically.
  function doUpload(f, namespace, lic, replace){
    // Lowercase unconditionally here (the authoritative client-side point), so the
    // query param and the live pending row match the server's lowercased name
    // regardless of how text reached the field — the input listener is then cosmetic.
    var name=(imageName.value||deriveName(f.name)).trim().toLowerCase();
    var qs=new URLSearchParams({ filename:f.name, namespace:namespace, name:name });
    if(replace) qs.set("replace","true");
    var key="u"+(++uploadSeq);
    var p={ key:key, displayName:name, namespace:namespace, total:f.size, isZip:true,
            phase:"Uploading", loaded:0, pct:0, speed:0, elapsed:0 };
    pendingUploads[key]=p; showTab("status"); resetUploadForm(); render();
    sendUpload(api("/api/upload")+"?"+qs.toString(), f, p, {
      onBodySent:function(){ p.phase="Unzipping"; paintPendingCell(p); },
      onDone:function(status, r){
        if(isConflictResponse(status, r)){
          delete pendingUploads[key]; render();
          var info=conflictInfo(r, name, namespace);
          askReplace(info.artifactName, info.namespace, function(){
            doUpload(f, namespace, lic, true);
          });
          return;
        }
        if(status>=200 && status<300 && r.ok){
          // The authoritative row now exists server-side; clear the pending row.
          delete pendingUploads[key];
          var what=(r.displayName||name), msg;
          if(r.nos==="srsim") msg="Uploaded "+what+" — SR-SIM image ready. Open Details for the sim NodeProfile and one-time setup."+(r.yangCreated?" YANG profile attached.":"");
          else if(r.nos==="sros") msg="Uploaded "+what+" — "+(r.fileCount||0)+" image files. "+(r.note||"");
          else msg="Uploaded "+what+"."+(r.md5?(" md5 "+r.md5+"."):"")+(r.yangCreated?" YANG profile attached.":"");
          if(lic){ attachLicense(r.artifactName||r.uploadId||name, what, lic, msg); }
          else { snack("ok", msg); refresh(); }
        } else { delete pendingUploads[key]; render();
          snack("err",(r.error||("HTTP "+status)), true); if(r.uploadId) refresh(); }
      },
      onError:function(){ delete pendingUploads[key]; render();
        snack("err","Network error during upload.", true); }
    });
  }

  btn.addEventListener("click", function(){
    var f=binFile.files[0];
    // Validate first; on failure keep the dialog open so the user can fix it.
    if(!f){ snack("err","Select a vendor .zip file first."); return; }
    if(!isZip(f.name)){ snack("err","Only vendor .zip images are supported (SR Linux or SR OS)."); return; }
    if(f.size>maxBytes){ snack("err","File is "+fmtBytes(f.size)+", over the "+fmtBytes(maxBytes)+" limit."); return; }
    var namespace=(ns.value||"").trim();
    if(!namespace){ snack("err","Choose a namespace first."); return; }
    var lic=(licText.value||"").trim();   // optional pasted license key
    if(lic && lic.length>262144){ snack("err","License text is too large (expected a small key)."); return; }
    if(lic && !looksLikeLicense(lic)){ snack("err","That doesn't look like a license key — paste the full “<node-id> <key>” line (extra spaces, quotes or a label are fine)."); return; }
    doUpload(f, namespace, lic);
  });

  // ---------- artifacts table ----------
  var pendingUploads={}, uploadSeq=0, lastImports=[];   // in-flight browser->controller uploads
  function chip(s){
    var c=s||"NoArtifact";
    if(c==="NoArtifact") return '<span class="chip c-NoArtifact" title="PVC bytes present but Artifact CR missing — controller will republish on reconcile">Needs republish</span>';
    return '<span class="chip c-'+c+'">'+esc(c)+'</span>';
  }
  function fmtElapsed(sec){ sec=Math.max(0,Math.floor(sec)); var m=Math.floor(sec/60), s=sec%60;
    return m+":"+(s<10?"0":"")+s; }
  function fmtEta(loaded, total, speedMbps, elapsed){
    if(!total || loaded >= total) return "0:00";
    if(speedMbps > 0.05){
      var rem = (total - loaded) / 1048576 / speedMbps;
      return fmtElapsed(rem);
    }
    if(elapsed > 0 && loaded > 0){
      var rate = loaded / elapsed;
      if(rate > 0) return fmtElapsed((total - loaded) / rate);
    }
    return "\u2014";
  }
  function isActiveStatus(s){
    return s === "InProgress" || s === "Uploading" || s === "Unzipping" ||
           s === "Processing" || s === "Pending";
  }
  function activeStatusCount(){
    var n = Object.keys(pendingUploads).length;
    currentData.forEach(function(t){
      if(isActiveStatus(t.downloadStatus)) n++;
    });
    lastImports.forEach(function(i){
      if(isActiveStatus(i.phase)) n++;
    });
    return n;
  }
  function updateStatusBadge(){
    var active = activeStatusCount();
    var badge = el("statusCount");
    if(!badge) return;
    if(active > 0){
      badge.style.display="inline-flex";
      if(badge.textContent !== String(active)){
        badge.textContent=active;
        badge.classList.remove("pop");
        void badge.offsetWidth;
        badge.classList.add("pop");
      }
    } else { badge.style.display="none"; badge.classList.remove("pop"); }
  }

  // ---------- KPI overview (dashboard cards) ----------
  function setKpi(id, val){
    var n = el(id);
    if(!n) return;
    var s = String(val);
    if(n.textContent !== s){
      n.textContent = s;
      n.classList.remove("bump"); void n.offsetWidth; n.classList.add("bump");
    }
  }
  function updateKpis(){
    var total=currentData.length, ready=0, act=Object.keys(pendingUploads).length, failed=0;
    currentData.forEach(function(t){
      var s=t.downloadStatus;
      if(s==="Available"||s==="Ready") ready++;
      else if(isActiveStatus(s)) act++;
      else if(s==="Error"||s==="Failed") failed++;
    });
    lastImports.forEach(function(i){ if(isActiveStatus(i.phase)) act++; });
    setKpi("kpiTotal", total);
    setKpi("kpiReady", ready);
    setKpi("kpiActive", act);
    setKpi("kpiFailed", failed);
  }

  function pendStatusHtml(p){
    if(p.phase==="Uploading"){
      var line=p.pct.toFixed(0)+"%  \u00b7  "+fmtBytes(p.loaded)+" / "+fmtBytes(p.total)+
               "  \u00b7  "+p.speed.toFixed(1)+" MB/s  \u00b7  "+
               fmtEta(p.loaded, p.total, p.speed, p.elapsed);
      return '<span class="chip c-Uploading">Uploading</span>'+
             '<div class="uprog"><div style="width:'+p.pct.toFixed(1)+'%"></div></div>'+
             '<div class="upinfo">'+esc(line)+'</div>';
    }
    var label = p.phase==="Unzipping" ? "Un-zipping" : "Finalizing";
    var sub   = p.phase==="Unzipping" ? "extracting image + reading md5" : "creating Artifact";
    return '<span class="chip c-'+p.phase+'">'+label+'</span>'+
           '<div class="uprog indet"><div></div></div>'+
           '<div class="upinfo">'+esc(sub)+'</div>';
  }
  function pendingRowHtml(p){
    return '<tr><td class="mono namecell">'+esc(p.displayName)+'</td><td>'+esc(p.namespace)+
      '</td><td class="num">'+fmtBytes(p.total)+'</td><td id="upstat-'+p.key+'">'+pendStatusHtml(p)+
      '</td><td></td></tr>';
  }
  function serverRowHtml(t){
    var reason=t.statusReason?('<div class="reason">'+esc(t.statusReason)+'</div>'):'';
    var fcount=(t.nos==="sros" && t.fileCount)?('<div class="upinfo">'+t.fileCount+' image files'+(t.yangStatus?' + yang':'')+'</div>'):'';
    var lic=t.license?('<div class="upinfo">+ license &middot; '+esc(t.licenseNos||'key')+'</div>'):'';
    var view=t.snippet
      ?('<button class="iconbtn primary ripple" data-act="view" data-uid="'+esc(t.uploadId||"")+'">Details</button> ')
      :'';
    var del='<button class="iconbtn del ripple" data-act="del" data-uid="'+esc(t.uploadId||"")+'" data-ns="'+esc(t.namespace||"")+'" data-name="'+esc(t.name||"")+'">Delete</button>';
    return '<tr><td class="mono namecell">'+esc(t.displayName||t.name)+fcount+lic+'</td><td>'+esc(t.namespace)+
      '</td><td class="num">'+fmtBytes(t.sizeBytes)+'</td><td>'+chip(t.downloadStatus)+reason+
      '</td><td style="white-space:nowrap">'+view+del+'</td></tr>';
  }

  function imDelete(uid, nsv, name){
    var t=null;
    for(var i=0;i<currentData.length;i++){ if(currentData[i].uploadId===uid){ t=currentData[i]; break; } }
    var label=name||uid||"this image";
    var hasYang=!!(t && t.yangStatus);
    var isSrsim=(t && t.nos==="srsim");
    var removes=isSrsim
      ? ("Removes the SR-SIM container image from this app's registry"
         +(hasYang?", and its YANG schema-profile Artifact":"")+".")
      : (t && t.nos==="sros")
      ? ('Removes all '+(t.fileCount||'the')+' boot-image Artifacts, their md5 Artifacts'
         +(hasYang?', and the YANG schema-profile Artifact':'')+' from EDA.')
      : ('Removes the image Artifact, its md5 Artifact'
         +(hasYang?', and the YANG schema-profile Artifact':'')+' from EDA.');
    var hostBullet=isSrsim
      ? "EDA's Digital Twin (eda-cx) can no longer pull this image — creating or restarting a sim that uses it will fail."
      : '<span class="mono">eda-asvr</span> stops hosting it — the served image URLs will return 404.';
    var lead='Permanently delete <b class="mono">'+esc(label)+'</b>'
             +(nsv?(' in <span class="mono">'+esc(nsv)+'</span>'):'')+'?';
    var bullets=[
      removes,
      hostBullet,
      'Any NodeProfile, node bootstrap (ZTP) or image upgrade that points at this image will fail until you re-add a valid image.',
      'This app holds the only durable copy, so its local file is deleted too — to restore it you must re-upload the vendor .zip.',
      'This cannot be undone.'
    ];
    if(t && t.license){ bullets.splice(1, 0, 'Also deletes the license ConfigMap <span class="mono">'+esc(t.license)+'</span> from <span class="mono">eda-system</span>.'); }
    askDelete(lead, bullets, function(){
      var qs=new URLSearchParams({uploadId:uid||"", namespace:nsv||"", name:name||""});
      fetch(api("/api/delete")+"?"+qs.toString(), {method:"POST"})
        .then(function(r){return r.json();})
        .then(function(d){ if(d && d.ok){ snack("ok","Deleted "+label+"."); refresh(); }
                           else { snack("err","Delete failed: "+((d&&d.error)||"unknown"), true); } })
        .catch(function(){ snack("err","Delete failed (network).", true); });
    });
  }

  // ---------- NodeProfile dialog (snippet + complete example) ----------
  var npSnippet=el("npSnippet"), npFull=el("npFull"), npCurrentUid=null;
  function copyBtn(btn, text){
    if(navigator.clipboard) navigator.clipboard.writeText(text||"");
    var t0=btn.textContent; btn.textContent="Copied"; setTimeout(function(){ btn.textContent=t0; }, 1200);
  }
  function openNodeProfile(uid){
    var t=null;
    for(var i=0;i<currentData.length;i++){ if(currentData[i].uploadId===uid){ t=currentData[i]; break; } }
    if(!t) return false;
    npCurrentUid=uid;
    el("npTitle").textContent = "NodeProfile — " + (t.displayName||t.name||"");
    // SR-SIM emits a containerImage-based sim NodeProfile, not a spec.images
    // fragment; relabel the snippet section + intro accordingly.
    var isSim=(t.nos==="srsim");
    el("npIntro").innerHTML = isSim
      ? 'Copy the <b>complete sim NodeProfile</b> below, or paste the <b>snippet</b> fields into an existing <span class="mono">NodeProfile</span>. The <span class="mono">containerImage</span>, version and <span class="mono">yang</span> are filled from this image; <span class="mono">&lt;…&gt;</span> values are for you to set.'
      : 'Paste the <b>snippet</b> into an existing <span class="mono">NodeProfile</span>\'s <span class="mono">spec.images</span>, or copy the <b>complete example</b> as a starting point. The image path(s), version, OS and <span class="mono">yang</span> are filled from this image; <span class="mono">&lt;…&gt;</span> values are for you to set.';
    if(t.license){
      el("npIntro").innerHTML += ' <b>License:</b> Image Manager created the ConfigMap '+
        '<span class="mono">'+esc(t.license)+'</span> in <span class="mono">eda-system</span> '+
        'from your uploaded key and referenced it in <span class="mono">spec.license</span> below.';
    }
    el("npSnipLabel").innerHTML = isSim
      ? 'Snippet &mdash; sim NodeProfile <span class="mono">spec</span>'
      : 'Snippet &mdash; <span class="mono">spec.images</span>';
    npSnippet.textContent = t.snippet || "(not ready yet)";
    npFull.textContent = t.nodeProfileExample || "(ready once the image is Available)";
    openModal(el("npDialog"));
    return true;
  }
  el("npClose").addEventListener("click", closeModal);
  el("npCopySnip").addEventListener("click", function(){ copyBtn(this, npSnippet.textContent); });
  el("npCopyFull").addEventListener("click", function(){ copyBtn(this, npFull.textContent); });
  el("npDelete").addEventListener("click", function(){
    var uid=npCurrentUid, t=null;
    if(!uid) return;
    for(var i=0;i<currentData.length;i++){ if(currentData[i].uploadId===uid){ t=currentData[i]; break; } }
    closeModal();
    imDelete(uid, (t&&t.namespace)||"", (t&&t.name)||"");
  });

  // Deep link from the EDA dashboard: /?details=<uploadId> opens that image's
  // details dialog (NodeProfile YAML + Delete) as soon as its row is loaded.
  var pendingDetails=(function(){
    try{ return new URLSearchParams(location.search).get("details")||null; }
    catch(e){ return null; }
  })();
  function tryPendingDetails(){
    if(!pendingDetails) return;
    if(openNodeProfile(pendingDetails)){
      pendingDetails=null;
      try{ history.replaceState(null, "", location.pathname); }catch(e){}
    }
  }

  rows.addEventListener("click", function(e){
    var b = e.target.closest("button[data-act]");
    if(!b) return;
    if(b.getAttribute("data-act")==="view"){
      openNodeProfile(b.getAttribute("data-uid"));
    } else if(b.getAttribute("data-act")==="del"){
      imDelete(b.getAttribute("data-uid"), b.getAttribute("data-ns"), b.getAttribute("data-name"));
    }
  });

  importRows.addEventListener("click", function(e){
    var b=e.target.closest("button[data-act='retry-import']");
    if(!b) return;
    var payload={
      url: b.getAttribute("data-url")||"",
      namespace: b.getAttribute("data-ns")||"",
      insecureSkipTLSVerify: !!el("urlInsecure").checked
    };
    var nm=(b.getAttribute("data-name")||"").trim();
    if(nm) payload.name=nm.toLowerCase();
    var m=/Artifact named '([^']+)' already exists in ([^.]+)/.exec(
      (b.parentElement&&b.parentElement.textContent)||"");
    if(m){
      askReplace(m[1], m[2].trim(), function(){ startUrlImport(payload, true); });
    } else {
      startUrlImport(payload, true);
    }
  });

  // sorting
  var STATUS_RANK={Available:0,Ready:0,InProgress:1,Error:2,Failed:3,NoArtifact:4};
  var currentData=[], sortState=null;  // null = server order (newest first)
  function sortData(arr){
    if(!sortState) return arr;
    var col=sortState.col, dir=sortState.dir, c=arr.slice();
    c.sort(function(a,b){
      var x,y;
      if(col==="sizeBytes"){ x=Number(a.sizeBytes||0); y=Number(b.sizeBytes||0); }
      else if(col==="downloadStatus"){ var rs=function(v){ return v in STATUS_RANK?STATUS_RANK[v]:9; };
        x=rs(a.downloadStatus); y=rs(b.downloadStatus); }
      else if(col==="displayName"){ x=(a.displayName||a.name||"").toLowerCase(); y=(b.displayName||b.name||"").toLowerCase(); }
      else { x=String(a[col]==null?"":a[col]).toLowerCase(); y=String(b[col]==null?"":b[col]).toLowerCase(); }
      if(x<y) return dir==="asc"?-1:1;
      if(x>y) return dir==="asc"?1:-1;
      return 0;
    });
    return c;
  }
  function paintHeaders(){
    var ths=document.querySelectorAll(".mtable th.sortable");
    ths.forEach(function(th){
      var col=th.getAttribute("data-sort");
      var arr=th.querySelector(".arr");
      if(sortState && sortState.col===col){
        th.classList.add("sorted"); arr.textContent = sortState.dir==="asc"?"▲":"▼";
      } else { th.classList.remove("sorted"); arr.textContent="↕"; }
    });
  }
  document.querySelectorAll(".mtable th.sortable").forEach(function(th){
    th.addEventListener("click", function(){
      var col=th.getAttribute("data-sort");
      if(sortState && sortState.col===col){ sortState.dir = sortState.dir==="asc"?"desc":"asc"; }
      else { sortState={col:col, dir:"asc"}; }
      paintHeaders(); render();
    });
  });
  paintHeaders();

  function render(){
    var serverRows=sortData(currentData);
    var seen={};
    currentData.forEach(function(t){ seen[(t.displayName||t.name)+"|"+t.namespace]=true; });
    var pend=[];
    Object.keys(pendingUploads).forEach(function(k){
      var p=pendingUploads[k];
      if(!seen[p.displayName+"|"+p.namespace]) pend.push(p);  // hide once the real artifact appears
    });
    updateKpis();
    if(!(pend.length+serverRows.length)){
      rows.innerHTML='<tr><td colspan="5" class="empty">No images yet.<br>'+
        '<button class="btn contained ripple" data-goto="upload">Upload an image</button> '+
        '<button class="btn text ripple" data-goto="url-import">Import from URL</button></td></tr>';
      el("statusCount").style.display="none"; return;
    }
    rows.innerHTML = pend.map(pendingRowHtml).join("") + serverRows.map(serverRowHtml).join("");
    updateStatusBadge();
  }
  rows.addEventListener("click", function(e){
    var g = e.target.closest("button[data-goto]");
    if(g) showTab(g.getAttribute("data-goto"));
  });

  function isImportConflict(i){
    return i.phase==="Failed" && /already exists/i.test(i.message||"");
  }
  function renderImports(list){
    lastImports = list || [];
    if(!list || !list.length){
      importRows.innerHTML='<tr><td colspan="5" class="empty">No URL imports yet.</td></tr>';
      if(activeTab === "status" || Object.keys(pendingUploads).length) render();
      return;
    }
    importRows.innerHTML = list.map(function(i){
      var retry=isImportConflict(i)
        ? (' <button class="btn text ripple" data-act="retry-import" data-url="'+esc(i.sourceUrl)+'"'+
           ' data-ns="'+esc(i.namespace)+'" data-name="'+esc(i.specName||"")+'">Replace</button>')
        : "";
      return '<tr><td class="mono">'+esc(i.name)+'</td><td>'+esc(i.namespace)+'</td>'+
        '<td class="mono">'+esc(i.sourceUrl)+'</td><td>'+chip(i.phase)+'</td>'+
        '<td>'+esc(i.message||"")+retry+'</td></tr>';
    }).join("");
    if(activeTab !== "status") render();
  }

  function refreshImports(){
    fetchJson(api("/api/imports")).then(function(res){
      if(res.status===401){ authReady=false; return ensureAuth().then(function(){ refreshImports(); }); }
      if(!res.ok){
        importRows.innerHTML='<tr><td colspan="5" class="empty">'+esc(
          "Could not load URL imports (HTTP "+res.status+").")+'</td></tr>';
        return;
      }
      renderImports((res.body||{}).imports||[]);
    }).catch(function(e){
      importRows.innerHTML='<tr><td colspan="5" class="empty">'+esc(
        "Failed to load URL imports: "+(e&&e.message?e.message:"network error"))+'</td></tr>';
    });
  }

  function loadSettings(){
    fetchJson(api("/api/settings")).then(function(res){
      if(!res.ok){ snack("err","Could not load settings (HTTP "+res.status+").", true); return; }
      var s=res.body||{};
      el("setDefaultNs").value=s.defaultArtifactNamespace||"";
      el("setDefaultRepo").value=s.defaultRepo||"";
      el("setMaxMiB").value=s.maxUploadMiB||4096;
      el("setPullBase").value=s.filePullBaseUrl||"";
      var meta=[];
      if(s.health) meta.push("Health: <span class='mono'>"+esc(s.health)+"</span>");
      if(s.version) meta.push("Controller: <span class='mono'>"+esc(s.version)+"</span>");
      if(s.message) meta.push(esc(s.message));
      el("settingsMeta").innerHTML = meta.length ? meta.join(" &middot; ") : "&mdash;";
      updateOpsHealth(s.health, s.message);
      if(el("opsStorageSub") && (s.filePullBaseUrl||"").trim())
        el("opsStorageSub").textContent="External pull URL: "+esc(s.filePullBaseUrl);
    });
  }
  el("settingsReload").addEventListener("click", loadSettings);
  el("settingsSave").addEventListener("click", function(){
    var body={
      defaultArtifactNamespace:(el("setDefaultNs").value||"").trim(),
      defaultRepo:(el("setDefaultRepo").value||"").trim(),
      maxUploadMiB:parseInt(el("setMaxMiB").value,10),
      filePullBaseUrl:(el("setPullBase").value||"").trim()
    };
    fetchJson(api("/api/settings"), {
      method:"PUT",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)
    }).then(function(res){
      if(res.ok && res.body && res.body.ok){
        if(res.body.settings && res.body.settings.maxUploadMiB)
          maxBytes=res.body.settings.maxUploadMiB*1024*1024;
        snack("ok","Settings saved.");
        loadSettings();
      } else {
        snack("err",(res.body&&res.body.error)||("Save failed (HTTP "+res.status+")"), true);
      }
    }).catch(function(){ snack("err","Save failed (network).", true); });
  });

  function startUrlImport(payload, replace){
    var body=Object.assign({}, payload);
    if(replace) body.replace=true;
    return fetchJson(api("/api/url-import"), {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)
    }).then(function(res){
      if(res.ok && res.body && res.body.ok){
        snack("ok","URL import started: "+res.body.namespace+"/"+res.body.name);
        el("urlSource").value=""; el("urlName").value=""; el("urlLicText").value="";
        showTab("status");
        refreshImports();
      } else if(isConflictResponse(res.status, res.body) && !replace){
        var info=conflictInfo(res.body, body.name||"", body.namespace||"");
        askReplace(info.artifactName, info.namespace, function(){ startUrlImport(payload, true); });
      } else {
        snack("err",(res.body&&res.body.error)||("Import failed (HTTP "+res.status+")"), true);
      }
    });
  }

  el("urlImportBtn").addEventListener("click", function(){
    var url=(el("urlSource").value||"").trim();
    var namespace=(urlNs.value||"").trim();
    var lic=(el("urlLicText").value||"").trim();
    if(!url){ snack("err","Enter a source URL."); return; }
    if(!/^https?:\/\//i.test(url)){ snack("err","URL must start with http:// or https://"); return; }
    if(!namespace){ snack("err","Choose a namespace first."); return; }
    if(lic && !looksLikeLicense(lic)){ snack("err","License text does not look valid."); return; }
    var payload={ url:url, namespace:namespace, insecureSkipTLSVerify:!!el("urlInsecure").checked };
    var nm=(el("urlName").value||"").trim();
    if(nm) payload.name=nm.toLowerCase();
    if(lic) payload.licenseKey=lic;
    startUrlImport(payload, false).catch(function(){ snack("err","Import failed (network).", true); });
  });

  function fmtGB(b){ return ((b||0)/1073741824).toFixed(1)+" GB"; }
  function updateStorage(s){
    if(!s) return;
    var pct=(typeof s.usedPercent==="number")?s.usedPercent:0;
    var fill=el("storageFill");
    fill.style.width=Math.max(0,Math.min(100,pct))+"%";
    fill.className="storage-fill"+(pct>=90?" crit":(pct>=75?" warn":""));
    el("storageStat").innerHTML='<span class="mono">'+pct+'%</span> used &ndash; <span class="mono">'+
      fmtGB(s.freeBytes)+'</span> free of <span class="mono">'+fmtGB(s.totalBytes)+'</span>';
  }

  function updateSystem(sys){
    if(!sys) return;
    var rec=sys.reconcile||{};
    var sm=el("opsStorageMode");
    if(sm) sm.textContent=(sys.storageBackend||"pvc").toUpperCase();
    var ss=el("opsStorageSub");
    if(ss){
      var ext=(sys.filePullBaseUrl||"").trim();
      ss.textContent=ext
        ? "External pull URL configured"
        : ((sys.deploymentMode||"single-replica")==="single-replica"
          ? "Single controller · RWO PVC (durable origin)"
          : (sys.deploymentMode||""));
    }
    var rv=el("opsReconcile");
    if(rv){
      var issues=(rec.incompleteDirs||[]).length+(rec.workDirsActive||0);
      if(issues) rv.textContent=issues+" attention";
      else if((rec.repushed||[]).length) rv.textContent="Self-healed";
      else rv.textContent="Up to date";
    }
    var rs=el("opsReconcileSub");
    if(rs){
      var bits=[];
      if(rec.at) bits.push("Last check "+rec.at.replace("T"," ").replace("Z"," UTC"));
      if((rec.repushed||[]).length) bits.push((rec.repushed||[]).length+" republish(es)");
      if((rec.staleWorkDirsRemoved||0)>0) bits.push(rec.staleWorkDirsRemoved+" stale temp dir(s) cleaned");
      rs.textContent=bits.length?bits.join(" · "):"Re-derives PVC vs Artifact state on startup";
    }
    var alert=el("opsAlert");
    if(alert){
      var msgs=[];
      if(rec.workDirsActive) msgs.push(rec.workDirsActive+" in-flight upload/import dir(s) on disk");
      if((rec.incompleteDirs||[]).length)
        msgs.push((rec.incompleteDirs||[]).length+" incomplete upload dir(s) without metadata — may need manual cleanup");
      if((rec.repushFailed||[]).length)
        msgs.push((rec.repushFailed||[]).length+" automatic republish failure(s) — see controller logs");
      if(msgs.length){
        alert.style.display="block";
        alert.innerHTML=msgs.map(function(m){ return "<span>"+esc(m)+"</span>"; }).join("");
      } else alert.style.display="none";
    }
  }

  function updateOpsHealth(health, message){
    var h=el("opsHealth"), m=el("opsHealthMsg");
    if(!h) return;
    var ok=(health||"ok").toLowerCase()==="ok";
    h.textContent=ok?"Ready":"Degraded";
    h.style.color=ok?"var(--ok-fg)":"var(--warn-fg)";
    if(m) m.textContent=message||"Single-replica · Recreate strategy";
  }

  function refresh(){
    fetchJson(api("/api/artifacts")).then(function(res){
      if(res.status===401){
        authReady=false;
        return ensureAuth().then(function(){ refresh(); });
      }
      if(!res.ok){
        rows.innerHTML='<tr><td colspan="5" class="empty">'+esc(
          "Could not load artifacts (HTTP "+res.status+").")+'</td></tr>';
        snack("err","Could not load artifacts (HTTP "+res.status+").", true);
        return;
      }
      var d=res.body||{};
      currentData=d.artifacts||[];
      updateStorage(d.storage);
      updateSystem(d.system);
      Object.keys(pendingUploads).forEach(function(k){
        var p=pendingUploads[k];
        if(currentData.some(function(t){ return (t.displayName||t.name)===p.displayName && t.namespace===p.namespace; }))
          delete pendingUploads[k];
      });
      render();
      tryPendingDetails();
    }).catch(function(e){
      rows.innerHTML='<tr><td colspan="5" class="empty">'+esc(
        "Failed to load artifacts: "+(e&&e.message?e.message:"network error"))+'</td></tr>';
    });
  }

  // ---------- theme toggle ----------
  function syncLiveIndicator(){
    var pill=el("liveIndicator");
    if(pill) pill.classList.toggle("active", authReady && !document.hidden);
  }
  (function(){
    var btn=el("themeBtn");
    if(!btn) return;
    btn.addEventListener("click", function(){
      var dark=document.documentElement.getAttribute("data-theme")==="dark";
      var next=dark?"light":"dark";
      document.documentElement.setAttribute("data-theme", next);
      try{ localStorage.setItem("imagemanager-theme", next); }catch(e){}
    });
  })();

  window.addEventListener("error", function(e){
    var msg = (e && e.message) ? e.message : "JavaScript error";
    setAuthBanner("err", "Image Manager failed to start: " + msg);
    bootDone();
  });

  // Adaptive reactive polling: 4s while anything is uploading/downloading,
  // 12s at rest; paused entirely while the tab is hidden.
  var pollTimer=null;
  function pollInterval(){ return activeStatusCount() > 0 ? 4000 : 12000; }
  function schedulePoll(){
    if(pollTimer) clearTimeout(pollTimer);
    pollTimer=setTimeout(function(){
      if(!document.hidden && authReady){
        if(activeTab==="status"){ refresh(); refreshImports(); }
        else { refresh(); }
      }
      syncLiveIndicator();
      schedulePoll();
    }, pollInterval());
  }
  document.addEventListener("visibilitychange", function(){
    if(!document.hidden && authReady){ refresh(); refreshImports(); }
    syncLiveIndicator();
  });
  var refreshBtn=el("refreshBtn");
  if(refreshBtn) refreshBtn.addEventListener("click", function(){ refresh(); refreshImports(); });
  schedulePoll();
  syncLiveIndicator();
})();
</script>
</body>
</html>
"""
