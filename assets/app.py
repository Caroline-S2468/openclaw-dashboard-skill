"""
OpenClaw Dashboard - Flask Application

A multi-page monitoring dashboard for OpenClaw agents, tasks, and skills.
Supports remote VPS sync via SSH.
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    DB_PATH, LOG_PATH,
    DASHBOARD_HOST, DASHBOARD_PORT, 
    DEBUG, REFRESH_INTERVAL, CONTROL_URL, API_KEY,
    VPS_HOST, print_config
)
from openclaw_monitor import OpenClawMonitor

app = Flask(__name__)

# Initialize monitor with OpenClaw path on VPS
# Since we're running ON the VPS, use local path
OPENCLAW_PATH = '/root/.openclaw'
monitor = OpenClawMonitor(OPENCLAW_PATH)

# VPS connected flag (for UI display)
ssh_initialized = bool(VPS_HOST)

# Navigation items for sidebar
NAV_ITEMS = [
    {'id': 'tasks', 'name': 'Tasks', 'icon': '📋', 'route': 'tasks_page'},
    {'id': 'agents', 'name': 'Agents', 'icon': '🤖', 'route': 'agents_page'},
    {'id': 'office', 'name': 'Office', 'icon': '🏢', 'route': 'office_page'},
    {'id': 'calendar', 'name': 'Calendar', 'icon': '📅', 'route': 'calendar_page'},
    {'id': 'memory', 'name': 'Memory', 'icon': '🧠', 'route': 'memory_page'},
    {'id': 'docs', 'name': 'Docs', 'icon': '📄', 'route': 'docs_page'},
    {'id': 'team', 'name': 'Team', 'icon': '👥', 'route': 'team_page'},
    {'id': 'factory', 'name': 'Factory', 'icon': '🏭', 'route': 'factory_page'},
]


def require_api_key(f):
    """Decorator to require API key for protected endpoints."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if API_KEY:  # Only check if API_KEY is set
            # Check header: X-API-Key
            provided_key = request.headers.get('X-API-Key')
            # Or check query parameter: ?api_key=...
            if not provided_key:
                provided_key = request.args.get('api_key')
            
            if provided_key != API_KEY:
                return jsonify({'success': False, 'error': 'Unauthorized - Invalid or missing API key'}), 401
        return f(*args, **kwargs)
    return decorated


# ============================================
# Page Routes
# ============================================

@app.route('/')
def index():
    """Redirect to tasks page."""
    return tasks_page()


@app.route('/tasks')
def tasks_page():
    """Tasks kanban board page."""
    return render_template('pages/tasks.html', 
                          nav_items=NAV_ITEMS, 
                          active_page='tasks',
                          refresh_interval=REFRESH_INTERVAL,
                          vps_connected=ssh_initialized)


@app.route('/agents')
def agents_page():
    """Agents list page."""
    return render_template('pages/agents.html',
                          nav_items=NAV_ITEMS,
                          active_page='agents',
                          refresh_interval=REFRESH_INTERVAL,
                          vps_connected=ssh_initialized)


@app.route('/office')
def office_page():
    """Office visualization page."""
    return render_template('pages/office.html',
                          nav_items=NAV_ITEMS,
                          active_page='office',
                          refresh_interval=REFRESH_INTERVAL,
                          vps_connected=ssh_initialized)


@app.route('/calendar')
def calendar_page():
    """Calendar schedule page."""
    return render_template('pages/calendar.html',
                          nav_items=NAV_ITEMS,
                          active_page='calendar',
                          refresh_interval=REFRESH_INTERVAL,
                          vps_connected=ssh_initialized)


@app.route('/memory')
def memory_page():
    """Memory/journal page."""
    return render_template('pages/memory.html',
                          nav_items=NAV_ITEMS,
                          active_page='memory',
                          refresh_interval=REFRESH_INTERVAL,
                          vps_connected=ssh_initialized)


@app.route('/docs')
def docs_page():
    """Documents page."""
    return render_template('pages/docs.html',
                          nav_items=NAV_ITEMS,
                          active_page='docs',
                          refresh_interval=REFRESH_INTERVAL,
                          vps_connected=ssh_initialized)


@app.route('/team')
def team_page():
    """Team/org chart page."""
    return render_template('pages/team.html',
                          nav_items=NAV_ITEMS,
                          active_page='team',
                          refresh_interval=REFRESH_INTERVAL,
                          vps_connected=ssh_initialized)


@app.route('/factory')
def factory_page():
    """Factory pipeline page."""
    return render_template('pages/factory.html',
                          nav_items=NAV_ITEMS,
                          active_page='factory',
                          refresh_interval=REFRESH_INTERVAL,
                          vps_connected=ssh_initialized)


# ============================================
# API Endpoints
# ============================================

@app.route('/api/dashboard')
@require_api_key
def api_dashboard():
    """Get all dashboard data as JSON."""
    try:
        # Force sync if connected to VPS
        if ssh_initialized and request.args.get('sync') == 'true':
            force_sync()
        
        tasks = monitor.get_tasks()
        agents = monitor.get_agents()
        skills = monitor.get_skills()
        stats = monitor.get_stats()
        logs = monitor.get_recent_logs(20)
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'source': 'vps' if ssh_initialized else 'local',
            'tasks': [
                {
                    'id': t.id,
                    'title': t.title,
                    'description': t.description,
                    'status': t.status,
                    'agent_id': t.agent_id,
                    'priority': t.priority,
                    'progress': t.progress,
                    'created_at': t.created_at.isoformat() if t.created_at else None,
                    'updated_at': t.updated_at.isoformat() if t.updated_at else None,
                    'skills_required': t.skills_required
                }
                for t in tasks
            ],
            'agents': [
                {
                    'id': a.id,
                    'name': a.name,
                    'status': a.status,
                    'current_task': a.current_task,
                    'skills': a.skills,
                    'last_heartbeat': a.last_heartbeat.isoformat() if a.last_heartbeat else None,
                    'total_tasks_completed': a.total_tasks_completed,
                    'uptime_minutes': a.uptime_minutes,
                    'role': getattr(a, 'role', 'Agent'),
                    'avatar': getattr(a, 'avatar', ''),
                }
                for a in agents
            ],
            'skills': [
                {
                    'name': s.name,
                    'description': s.description,
                    'category': s.category,
                    'enabled': s.enabled,
                    'used_count': s.used_count
                }
                for s in skills
            ],
            'stats': stats,
            'logs': logs
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tasks')
@require_api_key
def api_tasks():
    """Get tasks only."""
    try:
        tasks = monitor.get_tasks()
        return jsonify({
            'success': True,
            'tasks': [
                {
                    'id': t.id,
                    'title': t.title,
                    'description': t.description,
                    'status': t.status,
                    'agent_id': t.agent_id,
                    'priority': t.priority,
                    'progress': t.progress,
                    'created_at': t.created_at.isoformat() if t.created_at else None,
                    'updated_at': t.updated_at.isoformat() if t.updated_at else None,
                    'skills_required': t.skills_required
                }
                for t in tasks
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/agents')
@require_api_key
def api_agents():
    """Get agents only."""
    try:
        agents = monitor.get_agents()
        return jsonify({
            'success': True,
            'agents': [
                {
                    'id': a.id,
                    'name': a.name,
                    'status': a.status,
                    'current_task': a.current_task,
                    'skills': a.skills,
                    'last_heartbeat': a.last_heartbeat.isoformat() if a.last_heartbeat else None,
                    'total_tasks_completed': a.total_tasks_completed,
                    'uptime_minutes': a.uptime_minutes,
                    'role': getattr(a, 'role', 'Agent'),
                    'avatar': getattr(a, 'avatar', ''),
                }
                for a in agents
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/skills')
@require_api_key
def api_skills():
    """Get skills only."""
    try:
        skills = monitor.get_skills()
        return jsonify({
            'success': True,
            'skills': [
                {
                    'name': s.name,
                    'description': s.description,
                    'category': s.category,
                    'enabled': s.enabled,
                    'used_count': s.used_count
                }
                for s in skills
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stats')
@require_api_key
def api_stats():
    """Get statistics only."""
    try:
        stats = monitor.get_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs')
@require_api_key
def api_logs():
    """Get recent logs."""
    try:
        limit = request.args.get('limit', 50, type=int)
        logs = monitor.get_recent_logs(limit)
        return jsonify({
            'success': True,
            'logs': logs
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health')
def api_health():
    """Health check endpoint."""
    sync_status = None
    if ssh_initialized:
        try:
            from ssh_sync import get_ssh_manager, get_auto_sync
            ssh_mgr = get_ssh_manager()
            auto_sync = get_auto_sync()
            sync_status = {
                'connected': ssh_mgr is not None,
                'last_sync': ssh_mgr.get_last_sync_time().isoformat() if ssh_mgr and ssh_mgr.get_last_sync_time() else None,
                'synced': ssh_mgr.is_synced() if ssh_mgr else False,
                'auto_sync': auto_sync.get_stats() if auto_sync else None
            }
        except Exception as e:
            sync_status = {'error': str(e)}
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '2.0.0',
        'vps_connected': ssh_initialized,
        'sync': sync_status,
        'db_path': DB_PATH,
        'log_path': LOG_PATH
    })


@app.route('/api/sync', methods=['POST'])
@require_api_key
def api_sync():
    """Force a manual sync from VPS."""
    if not ssh_initialized:
        return jsonify({'success': False, 'error': 'VPS not configured'}), 400
    
    try:
        success = force_sync()
        return jsonify({
            'success': success,
            'timestamp': datetime.now().isoformat(),
            'message': 'Sync completed' if success else 'Sync failed'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# Template Filters
# ============================================

@app.template_filter('format_duration')
def format_duration(minutes):
    """Format minutes into human-readable duration."""
    if minutes < 60:
        return f"{minutes}m"
    elif minutes < 1440:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h {mins}m"
    else:
        days = minutes // 1440
        hours = (minutes % 1440) // 60
        return f"{days}d {hours}h"


@app.template_filter('time_ago')
def time_ago(dt_string):
    """Convert datetime to 'X time ago' format."""
    try:
        dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt
        
        seconds = int(diff.total_seconds())
        
        if seconds < 60:
            return f"{seconds}s ago"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        elif seconds < 86400:
            return f"{seconds // 3600}h ago"
        else:
            return f"{seconds // 86400}d ago"
    except:
        return dt_string


# ============================================
# Main Entry
# ============================================

if __name__ == '__main__':
    print_config()
    
    vps_info = f"VPS: {VPS_HOST}" if VPS_HOST else "Mode: Local"
    print(f"""
╔════════════════════════════════════════════════════════╗
║          OpenClaw Dashboard - Mission Control          ║
╠════════════════════════════════════════════════════════╣
║  URL: http://{DASHBOARD_HOST}:{DASHBOARD_PORT:<27} ║
║  {vps_info:<52} ║
║  OpenClaw: {OPENCLAW_PATH:<46} ║
╚════════════════════════════════════════════════════════╝
    """)
    
    app.run(
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        debug=DEBUG,
        threaded=True
    )
