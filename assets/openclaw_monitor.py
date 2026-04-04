"""
OpenClaw Monitor - File System Based

Reads agents, tasks, and data from OpenClaw's file system structure.
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Task:
    id: str
    title: str
    description: str
    status: str  # 'todo', 'in_progress', 'done', 'stuck'
    agent_id: Optional[str]
    agent_name: Optional[str]
    priority: str
    created_at: datetime
    updated_at: datetime
    skills_required: List[str]
    progress: int  # 0-100


@dataclass
class Agent:
    id: str
    name: str
    status: str  # 'idle', 'busy', 'stuck', 'offline'
    current_task: Optional[str]
    skills: List[str]
    last_heartbeat: datetime
    total_tasks_completed: int
    uptime_minutes: int
    role: str = 'Agent'
    avatar: str = '🤖'


@dataclass
class Skill:
    name: str
    description: str
    category: str
    enabled: bool
    used_count: int


class OpenClawMonitor:
    """Monitor for OpenClaw agents and tasks from file system."""
    
    def __init__(self, openclaw_path: str = '/root/.openclaw'):
        self.openclaw_path = Path(openclaw_path)
        self.agents_path = self.openclaw_path / 'agents'
        self.queue_path = self.openclaw_path / 'delivery-queue'
        self.log_path = self.openclaw_path / 'logs'
        self.workspace_path = self.openclaw_path / 'workspace'
        self.config_path = self.openclaw_path / 'openclaw.json'
        
        # Cache system
        self._cache = {}
        self._cache_timestamp = 0
        self._cache_ttl = 10  # Cache for 10 seconds

    def _get_cached(self, key: str, fetch_func):
        """Get cached data or fetch if expired."""
        now = datetime.now().timestamp()
        cache_key = f"{key}_{int(now) // self._cache_ttl}"
        
        if cache_key not in self._cache:
            self._cache[cache_key] = fetch_func()
            # Clean old cache entries
            current_bucket = int(now) // self._cache_ttl
            old_keys = [k for k in self._cache.keys() if int(k.split('_')[-1]) < current_bucket - 1]
            for k in old_keys:
                del self._cache[k]
        
        return self._cache[cache_key]
        
    def _read_json_file(self, path: Path) -> Optional[Dict]:
        """Read a JSON file safely."""
        try:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error reading {path}: {e}")
        return None
    
    def _read_jsonl_file(self, path: Path, limit: int = 100) -> List[Dict]:
        """Read a JSONL file safely."""
        entries = []
        try:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        if i >= limit:
                            break
                        try:
                            entries.append(json.loads(line.strip()))
                        except:
                            pass
        except Exception as e:
            print(f"Error reading {path}: {e}")
        return entries
    
    def _file_mod_time(self, path: Path) -> datetime:
        """Get file modification time."""
        try:
            stat = path.stat()
            return datetime.fromtimestamp(stat.st_mtime)
        except:
            return datetime.now() - timedelta(days=7)
    
    def _get_file_size(self, path: Path) -> int:
        """Get file size in bytes."""
        try:
            return path.stat().st_size
        except:
            return 0
    
    def get_agents(self) -> List[Agent]:
        """Fetch all agents from OpenClaw agents directory."""
        return self._get_cached('agents', self._fetch_agents)
    
    def _fetch_agents(self) -> List[Agent]:
        """Internal method to fetch agents data."""
        agents = []
        
        if not self.agents_path.exists():
            return self._get_mock_agents()
        
        try:
            # Read main config
            config = self._read_json_file(self.config_path) or {}
            agent_configs = config.get('agents', {})
            
            # Build agent name map from openclaw.json
            agent_name_map = {}
            agent_role_map = {}
            if 'list' in agent_configs:
                for agent_entry in agent_configs['list']:
                    if isinstance(agent_entry, dict):
                        agent_id = agent_entry.get('id')
                        agent_name = agent_entry.get('name', agent_id)
                        if agent_id:
                            agent_name_map[agent_id.lower()] = agent_name
                            if '_the_' in agent_name:
                                role = agent_name.split('_the_')[1].replace('_', ' ')
                                agent_role_map[agent_id.lower()] = role
            
            # Scan agents directory
            seen_agents = set()
            for agent_dir in self.agents_path.iterdir():
                if not agent_dir.is_dir():
                    continue
                    
                agent_id = agent_dir.name
                agent_id_lower = agent_id.lower()
                
                if '_workspace' in agent_id_lower:
                    continue
                base_id = agent_id_lower.replace('_agent', '')
                if base_id in seen_agents:
                    continue
                seen_agents.add(agent_id_lower)
                seen_agents.add(base_id)
                
                # Get real name from openclaw.json
                if agent_id_lower == 'main':
                    real_name = 'Edgar'
                    role = 'Main Agent'
                else:
                    real_name = agent_name_map.get(agent_id_lower, agent_id)
                    role = agent_role_map.get(agent_id_lower, 'Agent')
                    if '_agent' in real_name.lower():
                        real_name = real_name.replace('_agent', '').replace('_Agent', '')
                
                # Read agent directory config
                agent_config_file = agent_dir / 'config.json'
                agent_config = self._read_json_file(agent_config_file) or {}
                
                if agent_config.get('name'):
                    real_name = agent_config.get('name')
                if agent_config.get('role') or agent_config.get('title'):
                    role = agent_config.get('role', agent_config.get('title', role))
                
                # Determine agent status based on recent activity
                last_active = self._get_agent_last_active(agent_dir, agent_id)
                minutes_since_active = (datetime.now() - last_active).total_seconds() / 60
                
                # Check for active sessions
                has_active_session = self._has_active_session(agent_dir)
                
                if has_active_session or minutes_since_active < 5:
                    status = 'busy'
                elif minutes_since_active < 30:
                    status = 'idle'
                else:
                    status = 'offline'
                
                # Get skills from config
                skills = agent_config.get('skills', [])
                if not skills and 'systemPrompt' in str(agent_config):
                    skills = self._extract_skills_from_prompt(str(agent_config.get('systemPrompt', '')))
                
                # Assign default skills based on agent name/role if no skills found
                if not skills or skills == ['general']:
                    skills = self._get_default_skills_for_agent(real_name, role)
                
                # Get avatar emoji
                avatar = self._get_agent_avatar(real_name, role)
                
                # Count completed tasks
                completed_tasks = self._count_agent_tasks(agent_id)
                
                # Get current task
                current_task = self._get_agent_current_task(agent_id, real_name)
                
                agents.append(Agent(
                    id=agent_id,
                    name=real_name.replace('_', ' '),
                    status=status,
                    current_task=current_task,
                    skills=skills[:8] if skills else ['general'],
                    last_heartbeat=last_active,
                    total_tasks_completed=completed_tasks,
                    uptime_minutes=int(24 * 60),
                    role=role,
                    avatar=avatar
                ))
            
            if not agents:
                return self._get_mock_agents()
                
        except Exception as e:
            print(f"Error reading agents: {e}")
            return self._get_mock_agents()
        
        return agents
    
    def _get_agent_last_active(self, agent_dir: Path, agent_id: str = '') -> datetime:
        """Get last active time for an agent."""
        latest = datetime.now() - timedelta(days=7)
        
        try:
            # Only check top-level files and immediate subdirectories (limit depth)
            # Check files in agent_dir
            for file in agent_dir.iterdir():
                if file.is_file():
                    mod_time = self._file_mod_time(file)
                    if mod_time > latest:
                        latest = mod_time
                elif file.is_dir() and file.name in ['sessions', 'memory']:
                    # Only check specific subdirs, limit depth to 2
                    for subfile in file.iterdir():
                        if subfile.is_file():
                            mod_time = self._file_mod_time(subfile)
                            if mod_time > latest:
                                latest = mod_time
            
            # For main agent, only check recent workspace files (limit to 10)
            if agent_id.lower() == 'main' and self.workspace_path.exists():
                recent_files = []
                for file in self.workspace_path.glob('*.md'):
                    if file.is_file():
                        recent_files.append((file, self._file_mod_time(file)))
                # Sort and take top 10
                recent_files.sort(key=lambda x: x[1], reverse=True)
                for file, mod_time in recent_files[:10]:
                    if mod_time > latest:
                        latest = mod_time
                        break
                            
        except Exception as e:
            print(f"Error checking agent activity: {e}")
        
        return latest
    
    def _has_active_session(self, agent_dir: Path) -> bool:
        """Check if agent has an active session (large sessions.json)."""
        try:
            sessions_file = agent_dir / 'sessions' / 'sessions.json'
            if sessions_file.exists():
                # Check if modified in last hour and has content
                mod_time = self._file_mod_time(sessions_file)
                size = self._get_file_size(sessions_file)
                minutes_ago = (datetime.now() - mod_time).total_seconds() / 60
                return minutes_ago < 60 and size > 1000  # Active if > 1KB and recent
        except:
            pass
        return False
    
    def _get_agent_current_task(self, agent_id: str, agent_name: str) -> Optional[str]:
        """Get current task for an agent."""
        try:
            # Check workspace for recent files by this agent
            if self.workspace_path.exists() and agent_id.lower() == 'main':
                recent_files = []
                for file in self.workspace_path.rglob('*.md'):
                    if file.is_file() and 'venv' not in str(file):
                        mod_time = self._file_mod_time(file)
                        minutes_ago = (datetime.now() - mod_time).total_seconds() / 60
                        if minutes_ago < 240:  # 4 hours
                            recent_files.append((file, mod_time))
                
                if recent_files:
                    recent_files.sort(key=lambda x: x[1], reverse=True)
                    return recent_files[0][0].stem.replace('-', ' ').title()
            
            # Check sessions
            agent_dir = self.agents_path / agent_id
            sessions_file = agent_dir / 'sessions' / 'sessions.json'
            if sessions_file.exists():
                size = self._get_file_size(sessions_file)
                if size > 10000:  # Large session file indicates active work
                    return 'Active Session'
                    
        except:
            pass
        return None
    
    def _count_agent_tasks(self, agent_id: str) -> int:
        """Count tasks associated with an agent."""
        count = 0
        try:
            workspace_path = self.openclaw_path / 'workspace'
            if workspace_path.exists():
                # Limit search to top-level files only
                for item in workspace_path.iterdir():
                    if agent_id.lower() in item.name.lower():
                        count += 1
        except:
            pass
        return count
    

    def _get_default_skills_for_agent(self, name: str, role: str) -> List[str]:
        """Get default skills based on agent name and role."""
        name_lower = name.lower()
        role_lower = role.lower() if role else ''
        
        # Define skill mappings
        skill_mappings = {
            'edgar': ['management', 'coordination', 'planning', 'delegation'],
            'charlotte': ['skill_management', 'training', 'optimization', 'analysis'],
            'anne': ['coding', 'development', 'debugging', 'code_review', 'git'],
            'danny': ['circularity', 'sustainability', 'research', 'analysis'],
            'emily': ['information_gathering', 'research', 'analysis', 'documentation'],
            'laosun': ['wisdom', 'consulting', 'strategy', 'mentoring'],
            '老孙': ['wisdom', 'consulting', 'strategy', 'mentoring'],
        }
        
        # Check name mapping
        for key, skills in skill_mappings.items():
            if key in name_lower:
                return skills
        
        # Role-based fallback
        role_skills = {
            'developer': ['coding', 'development', 'debugging'],
            'skillmaster': ['skill_management', 'training', 'optimization'],
            'circularity': ['sustainability', 'research', 'analysis'],
            'infoexpert': ['research', 'information_gathering', 'analysis'],
            'researcher': ['research', 'analysis', 'documentation'],
            'writer': ['writing', 'editing', 'documentation'],
        }
        
        for key, skills in role_skills.items():
            if key in role_lower:
                return skills
        
        return ['general']

    def _extract_skills_from_prompt(self, prompt: str) -> List[str]:
        """Extract skills from system prompt."""
        skill_keywords = [
            'coding', 'programming', 'writing', 'research', 'analysis',
            'design', 'testing', 'debugging', 'documentation', 'review',
            'planning', 'communication', 'management', 'optimization'
        ]
        found_skills = []
        prompt_lower = prompt.lower()
        for skill in skill_keywords:
            if skill in prompt_lower:
                found_skills.append(skill)
        return found_skills[:5] if found_skills else ['general']
    
    def _get_agent_avatar(self, name: str, role: str) -> str:
        """Get avatar emoji for agent."""
        name_lower = name.lower()
        role_lower = role.lower()
        
        if name_lower == 'edgar':
            return '👑'
        
        name_emojis = {
            'anne': '👩‍💻',
            'charlotte': '👩‍🔬',
            'danny': '👨‍🔧',
            'emily': '👩‍💼',
            '老孙': '👴',
            'laosun': '👴',
        }
        
        for key, emoji in name_emojis.items():
            if key in name_lower:
                return emoji
        
        role_emojis = {
            'developer': '👨‍💻',
            'skillmaster': '🎯',
            'circularity': '♻️',
            'infoexpert': '📊',
            'researcher': '🔍',
            'writer': '📝',
            'designer': '🎨',
            'manager': '👔',
            'analyst': '📈',
            'tester': '🔧',
            'expert': '🎓',
        }
        
        for key, emoji in role_emojis.items():
            if key in role_lower:
                return emoji
        
        default_emojis = ['🤖', '👤', '🧑', '👨', '👩', '🦸', '🦹', '🧙']
        return default_emojis[hash(name) % len(default_emojis)]
    
    def get_tasks(self) -> List[Task]:
        """Fetch all tasks from various sources."""
        return self._get_cached('tasks', self._fetch_tasks)
    
    def _fetch_tasks(self) -> List[Task]:
        """Internal method to fetch tasks data."""
        tasks = []
        
        try:
            # 1. Get active sessions as in-progress tasks
            session_tasks = self._get_session_tasks()
            tasks.extend(session_tasks)
            
            # 2. Get workspace work as tasks
            workspace_tasks = self._get_workspace_tasks()
            tasks.extend(workspace_tasks)
            
            # 3. Get delivery queue tasks
            queue_tasks = self._get_queue_tasks()
            tasks.extend(queue_tasks)
            
            # Sort: in_progress first, then by updated time
            tasks.sort(key=lambda t: (0 if t.status == 'in_progress' else 1, t.updated_at), reverse=False)
            
            # Re-sort by updated time but keep priority
            in_progress_tasks = [t for t in tasks if t.status == 'in_progress']
            other_tasks = [t for t in tasks if t.status != 'in_progress']
            other_tasks.sort(key=lambda t: t.updated_at, reverse=True)
            
            # Combine and limit
            tasks = in_progress_tasks + other_tasks
            tasks = tasks[:100]
            
            # Final sort by updated time
            tasks.sort(key=lambda t: t.updated_at, reverse=True)
            
            if not tasks:
                return self._get_mock_tasks()
                
        except Exception as e:
            print(f"Error reading tasks: {e}")
            return self._get_mock_tasks()
        
        return tasks
    
    def _get_session_tasks(self) -> List[Task]:
        """Get tasks from active sessions."""
        tasks = []
        
        try:
            for agent_dir in self.agents_path.iterdir():
                if not agent_dir.is_dir():
                    continue
                
                agent_id = agent_dir.name
                if '_workspace' in agent_id.lower():
                    continue
                
                # Get agent name
                if agent_id.lower() == 'main':
                    agent_name = 'Edgar'
                else:
                    config = self._read_json_file(self.config_path) or {}
                    agent_list = config.get('agents', {}).get('list', [])
                    agent_name = agent_id
                    for entry in agent_list:
                        if isinstance(entry, dict) and entry.get('id') == agent_id:
                            agent_name = entry.get('name', agent_id)
                            break
                
                # Check sessions
                sessions_file = agent_dir / 'sessions' / 'sessions.json'
                if sessions_file.exists():
                    mod_time = self._file_mod_time(sessions_file)
                    size = self._get_file_size(sessions_file)
                    minutes_ago = (datetime.now() - mod_time).total_seconds() / 60
                    
                    # Active session (large file, modified recently)
                    if minutes_ago < 240 and size > 1000:
                        tasks.append(Task(
                            id=f'session-{agent_id}-{int(mod_time.timestamp())}',
                            title=f'Active Session with {agent_name}',
                            description=f'Real-time conversation in progress ({size//1024}KB session data)',
                            status='in_progress',
                            agent_id=agent_id,
                            agent_name=agent_name.replace('_', ' '),
                            priority='high',
                            created_at=mod_time,
                            updated_at=mod_time,
                            skills_required=['conversation', 'session'],
                            progress=65
                        ))
                    # Recent but not active
                    elif minutes_ago < 240 and size > 100:
                        tasks.append(Task(
                            id=f'session-{agent_id}-{int(mod_time.timestamp())}',
                            title=f'Recent Session with {agent_name}',
                            description=f'Session data available ({size//1024}KB)',
                            status='todo',
                            agent_id=agent_id,
                            agent_name=agent_name.replace('_', ' '),
                            priority='medium',
                            created_at=mod_time,
                            updated_at=mod_time,
                            skills_required=['conversation'],
                            progress=30
                        ))
                        
        except Exception as e:
            print(f"Error reading sessions: {e}")
        
        return tasks
    
    def _get_workspace_tasks(self) -> List[Task]:
        """Get tasks from workspace files."""
        tasks = []
        
        try:
            if not self.workspace_path.exists():
                return tasks
            
            now = datetime.now()
            
            # Find recently modified .md files (excluding venv)
            recent_files = []
            for file in self.workspace_path.rglob('*.md'):
                if file.is_file() and 'venv' not in str(file) and 'node_modules' not in str(file):
                    mod_time = self._file_mod_time(file)
                    minutes_ago = (now - mod_time).total_seconds() / 60
                    
                    if minutes_ago < 240:  # 4 hours
                        recent_files.append((file, mod_time, minutes_ago))
            
            # Sort by most recent
            recent_files.sort(key=lambda x: x[1], reverse=True)
            
            # Create tasks
            for file, mod_time, minutes_ago in recent_files[:10]:
                task_name = file.stem.replace('-', ' ').title()
                
                # Determine status based on recency
                if minutes_ago < 60:
                    status = 'in_progress'
                    progress = 70
                    priority = 'high'
                elif minutes_ago < 120:
                    status = 'in_progress'
                    progress = 50
                    priority = 'medium'
                else:
                    status = 'todo'
                    progress = 30
                    priority = 'low'
                
                tasks.append(Task(
                    id=f'workspace-{file.stem}',
                    title=task_name[:60],
                    description=f'Working on {file.name}',
                    status=status,
                    agent_id='main',
                    agent_name='Edgar',
                    priority=priority,
                    created_at=mod_time,
                    updated_at=mod_time,
                    skills_required=['workspace', 'documentation'],
                    progress=progress
                ))
                
        except Exception as e:
            print(f"Error reading workspace: {e}")
        
        return tasks
    
    def _get_queue_tasks(self) -> List[Task]:
        """Get tasks from delivery queue."""
        tasks = []
        
        try:
            if not self.queue_path.exists():
                return tasks
            
            # Read pending tasks
            for task_file in self.queue_path.glob('*.json'):
                if task_file.is_file():
                    task_data = self._read_json_file(task_file)
                    if task_data:
                        tasks.append(self._parse_queue_task(task_data, 'todo'))
            
            # Read failed tasks
            failed_path = self.queue_path / 'failed'
            if failed_path.exists():
                for task_file in failed_path.glob('*.json'):
                    if task_file.is_file():
                        task_data = self._read_json_file(task_file)
                        if task_data:
                            tasks.append(self._parse_queue_task(task_data, 'stuck'))
                            
        except Exception as e:
            print(f"Error reading queue: {e}")
        
        return tasks
    
    def _parse_queue_task(self, task_data: Dict, default_status: str) -> Task:
        """Parse task data from delivery queue JSON."""
        task_id = task_data.get('id', 'unknown')
        enqueued_at = task_data.get('enqueuedAt', 0)
        
        if enqueued_at:
            created_at = datetime.fromtimestamp(enqueued_at / 1000)
        else:
            created_at = datetime.now()
        
        # Extract title from payloads
        payloads = task_data.get('payloads', [])
        title = 'Task'
        description = ''
        
        if payloads and len(payloads) > 0:
            first_payload = payloads[0]
            if isinstance(first_payload, dict):
                text = first_payload.get('text', '')
                if text:
                    lines = text.split('\n')
                    title = lines[0][:60]
                    description = '\n'.join(lines[1:3])[:200]
        
        # Determine priority
        retry_count = task_data.get('retryCount', 0)
        if retry_count > 3:
            priority = 'critical'
        elif retry_count > 1:
            priority = 'high'
        else:
            priority = 'medium'
        
        # Determine status
        last_error = task_data.get('lastError')
        if last_error:
            status = 'stuck'
        else:
            status = default_status
        
        # Extract channel info
        channel = task_data.get('channel', '')
        to = task_data.get('to', '')
        skills = []
        if channel:
            skills.append(channel)
        if to:
            skills.append(to)
        
        return Task(
            id=task_id,
            title=title,
            description=description,
            status=status,
            agent_id=None,
            agent_name=None,
            priority=priority,
            created_at=created_at,
            updated_at=datetime.now(),
            skills_required=skills,
            progress=0 if status in ['todo', 'stuck'] else 50
        )
    
    def get_skills(self) -> List[Skill]:
        """Fetch skills from agent configurations."""
        return self._get_cached('skills', self._fetch_skills)
    
    def _fetch_skills(self) -> List[Skill]:
        """Internal method to fetch skills data."""
        skills_map = {}
        
        agents = self.get_agents()
        for agent in agents:
            for skill_name in agent.skills:
                if skill_name not in skills_map:
                    skills_map[skill_name] = {'count': 0, 'agents': []}
                skills_map[skill_name]['count'] += 1
                skills_map[skill_name]['agents'].append(agent.name)
        
        skills = []
        for name, data in sorted(skills_map.items()):
            skills.append(Skill(
                name=name,
                description=f"Used by {', '.join(data['agents'][:3])}",
                category='general',
                enabled=True,
                used_count=data['count']
            ))
        
        if not skills:
            return self._get_mock_skills()
        
        return skills
    
    def get_stats(self) -> Dict[str, Any]:
        """Get overall statistics."""
        tasks = self.get_tasks()
        agents = self.get_agents()
        skills = self.get_skills()
        
        task_status_counts = {
            'todo': len([t for t in tasks if t.status == 'todo']),
            'in_progress': len([t for t in tasks if t.status == 'in_progress']),
            'done': len([t for t in tasks if t.status == 'done']),
            'stuck': len([t for t in tasks if t.status == 'stuck']),
        }
        
        agent_status_counts = {
            'idle': len([a for a in agents if a.status == 'idle']),
            'busy': len([a for a in agents if a.status == 'busy']),
            'stuck': len([a for a in agents if a.status == 'stuck']),
            'offline': len([a for a in agents if a.status == 'offline']),
        }
        
        return {
            'total_tasks': len(tasks),
            'total_agents': len(agents),
            'total_skills': len(skills),
            'task_status': task_status_counts,
            'agent_status': agent_status_counts,
            'completion_rate': self._calculate_completion_rate(tasks),
        }
    
    def get_recent_logs(self, lines: int = 50) -> List[Dict]:
        """Fetch recent log entries."""
        logs = []
        
        if not self.log_path.exists():
            return logs
        
        try:
            commands_log = self.log_path / 'commands.log'
            if commands_log.exists():
                with open(commands_log, 'r') as f:
                    file_lines = f.readlines()
                    for line in file_lines[-lines:]:
                        parsed = self._parse_log_line(line.strip())
                        if parsed:
                            logs.append(parsed)
            
            return sorted(logs, key=lambda x: x.get('timestamp', ''), reverse=True)[:lines]
        except Exception as e:
            print(f"Error reading logs: {e}")
            return []
    
    def _parse_log_line(self, line: str) -> Optional[Dict]:
        """Parse a single log line."""
        if not line:
            return None
        
        # Try to parse as JSON first
        try:
            data = json.loads(line)
            return {
                'timestamp': data.get('timestamp', datetime.now().isoformat()),
                'level': 'INFO',
                'message': f"{data.get('action', 'unknown')} from {data.get('source', 'unknown')}"
            }
        except:
            pass
        
        # Fallback to regex
        patterns = [
            r'(?P<timestamp>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}).*?(?P<level>INFO|WARN|ERROR|DEBUG).*?(?P<message>.+)',
            r'\[(?P<timestamp>[^\]]+)\].*?(?P<message>.+)',
        ]
        
        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                groups = match.groupdict()
                return {
                    'timestamp': groups.get('timestamp', datetime.now().isoformat()),
                    'level': groups.get('level', 'INFO'),
                    'message': groups.get('message', line)[:200]
                }
        
        return {
            'timestamp': datetime.now().isoformat(),
            'level': 'INFO',
            'message': line[:200]
        }
    
    def _calculate_completion_rate(self, tasks: List[Task]) -> float:
        """Calculate task completion rate."""
        if not tasks:
            return 0.0
        done = len([t for t in tasks if t.status == 'done'])
        return round(done / len(tasks) * 100, 1)
    
    # Mock data generators
    def _get_mock_tasks(self) -> List[Task]:
        return [
            Task('1', 'Research competitors', 'Analyze top 3 competitors', 'in_progress', 'agent-1', 'Edgar', 'high', datetime.now() - timedelta(hours=2), datetime.now(), ['web_search', 'analysis'], 45),
            Task('2', 'Draft email campaign', 'Write Q2 marketing emails', 'todo', None, None, 'medium', datetime.now() - timedelta(hours=4), datetime.now(), ['writing'], 0),
            Task('3', 'Code review', 'Review PR #234', 'done', 'agent-2', 'Anne', 'high', datetime.now() - timedelta(days=1), datetime.now(), ['coding'], 100),
            Task('4', 'Fix database bug', 'Resolve connection issue', 'stuck', 'agent-1', 'Edgar', 'critical', datetime.now() - timedelta(hours=1), datetime.now(), ['coding', 'database'], 20),
            Task('5', 'Update documentation', 'Add API docs', 'todo', None, None, 'low', datetime.now() - timedelta(hours=3), datetime.now(), ['writing'], 0),
        ]
    
    def _get_mock_agents(self) -> List[Agent]:
        return [
            Agent('agent-1', 'Edgar', 'busy', 'Research competitors', ['web_search', 'coding', 'analysis'], datetime.now() - timedelta(minutes=5), 42, 360, 'Main Agent', '👑'),
            Agent('agent-2', 'Anne', 'idle', None, ['coding', 'debugging', 'git'], datetime.now() - timedelta(minutes=2), 28, 240, 'Developer', '👩‍💻'),
            Agent('agent-3', 'Charlotte', 'stuck', 'Fix database bug', ['writing', 'translation'], datetime.now() - timedelta(minutes=30), 15, 120, 'Writer', '📝'),
        ]
    
    def _get_mock_skills(self) -> List[Skill]:
        return [
            Skill('web_search', 'Search the web for information', 'research', True, 156),
            Skill('coding', 'Write and review code', 'development', True, 89),
            Skill('analysis', 'Analyze data and reports', 'research', True, 67),
            Skill('writing', 'Write and edit content', 'content', True, 134),
            Skill('database', 'Database operations', 'development', True, 45),
        ]
