# ============================================================================
# TianShu 一键启动脚本 (Windows / PowerShell)
# ============================================================================
#
# 使用方法:
#   .\quick-start.ps1           # 一键启动后端 + 前端
#   .\quick-start.ps1 -Stop     # 停止所有服务
#   .\quick-start.ps1 -Restart  # 重启所有服务
#   .\quick-start.ps1 -Status   # 查看服务状态
#
# 端口约定:
#   - 后端 Gateway: 127.0.0.1:8001
#   - 前端 Next.js: 127.0.0.1:3000
#
# 配置文件:
#   - 项目根: .\config.yaml (后端)
#   - 前端:    .\frontend\.env.local
#   - 环境变量: .\quick-start.env (一键启动专用, 不存在时自动创建)
#
# ============================================================================

param(
    [switch]$Stop,
    [switch]$Restart,
    [switch]$Status,
    [switch]$Seed,        # 启动后插入种子 Agent + 工作流
    [switch]$NoAuth,      # 跳过认证 (开发模式)
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------------
# 路径与常量
# ----------------------------------------------------------------------------
$Root      = $PSScriptRoot
$Backend   = Join-Path $Root "backend"
$Frontend  = Join-Path $Root "frontend"
$LogsDir   = Join-Path $Root ".run-logs"
$BackendLogOut = Join-Path $LogsDir "backend.out.log"
$BackendLogErr = Join-Path $LogsDir "backend.err.log"
$FrontendLogOut = Join-Path $LogsDir "frontend.out.log"
$FrontendLogErr = Join-Path $LogsDir "frontend.err.log"
$BackendPidFile = Join-Path $LogsDir "backend.pid"
$FrontendPidFile = Join-Path $LogsDir "frontend.pid"
$EnvFile   = Join-Path $Root "quick-start.env"

$BackendPort  = 8001
$FrontendPort = 3000
$VenvPython   = Join-Path $Backend ".venv\Scripts\python.exe"

# ----------------------------------------------------------------------------
# 帮助
# ----------------------------------------------------------------------------
if ($Help) {
    Write-Host @"
TianShu 一键启动脚本

用法:
  .\quick-start.ps1                # 启动后端 + 前端
  .\quick-start.ps1 -Stop          # 停止所有服务
  .\quick-start.ps1 -Restart       # 重启所有服务
  .\quick-start.ps1 -Status        # 查看服务状态
  .\quick-start.ps1 -Seed          # 启动后插入演示 Agent + 工作流
  .\quick-start.ps1 -NoAuth        # 禁用认证 (开发模式)

访问地址:
  前端:        http://localhost:$FrontendPort
  后端 API:    http://127.0.0.1:$BackendPort
  工作流 API:  http://127.0.0.1:$BackendPort/api/workflows
  智能体 API:  http://127.0.0.1:$BackendPort/api/agents
  聊天 API:    http://127.0.0.1:$BackendPort/api/v1/chat

日志:
  后端:  $BackendLog
  前端:  $FrontendLog
"@
    exit 0
}

# ----------------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------------
function Write-Step($msg) { Write-Host "▶ $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  ⚠ $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  ✗ $msg" -ForegroundColor Red }

function Ensure-Dir($path) {
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

function Test-PortListening($port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

function Kill-Port($port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        foreach ($c in $conn) {
            $procId = $c.OwningProcess
            if ($procId -gt 0) {
                try {
                    Stop-Process -Id $procId -Force -ErrorAction Stop
                    Write-Warn "Killed process on port $port (PID=$procId)"
                } catch {
                    Write-Warn "Failed to kill PID=$procId : $_"
                }
            }
        }
    }
}

function Read-PidFile($file) {
    if (Test-Path $file) {
        $savedPid = Get-Content $file -ErrorAction SilentlyContinue
        if ($savedPid -match '^\d+$') {
            $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
            if ($proc) { return $proc }
        }
    }
    return $null
}

function Ensure-Venv {
    if (-not (Test-Path $VenvPython)) {
        Write-Warn "Backend venv not found at $VenvPython"
        Write-Step "Creating venv via uv sync ..."
        Push-Location $Backend
        try {
            & uv sync
            if ($LASTEXITCODE -ne 0) {
                throw "uv sync failed (exit code $LASTEXITCODE)"
            }
        } finally {
            Pop-Location
        }
        if (-not (Test-Path $VenvPython)) {
            throw "venv still missing after uv sync"
        }
        Write-Ok "venv ready"
    }
}

function Ensure-FrontendDeps {
    $nodeModules = Join-Path $Frontend "node_modules"
    if (-not (Test-Path $nodeModules)) {
        Write-Warn "Frontend node_modules not found"
        Write-Step "Installing frontend deps via pnpm ..."
        Push-Location $Frontend
        try {
            $pnpm = Join-Path $Root "scripts\pnpm.py"
            & python $pnpm install
            if ($LASTEXITCODE -ne 0) {
                throw "pnpm install failed (exit code $LASTEXITCODE)"
            }
        } finally {
            Pop-Location
        }
        Write-Ok "frontend deps ready"
    }
}

function Ensure-Config {
    # 后端 config.yaml
    $configYaml = Join-Path $Root "config.yaml"
    if (-not (Test-Path $configYaml)) {
        $example = Join-Path $Root "config.example.yaml"
        if (Test-Path $example) {
            Copy-Item $example $configYaml
            Write-Warn "Created config.yaml from example - please fill in your API keys!"
        } else {
            throw "Neither config.yaml nor config.example.yaml exists"
        }
    }

    # 前端 .env.local
    $frontendEnv = Join-Path $Frontend ".env.local"
    if (-not (Test-Path $frontendEnv)) {
        $example = Join-Path $Frontend ".env.example"
        if (Test-Path $example) {
            Copy-Item $example $frontendEnv
            Write-Ok "Created frontend\.env.local from example"
        }
    }
}

function Ensure-EnvFile {
    # 创建一键启动专用环境变量文件
    if (-not (Test-Path $EnvFile)) {
        @"
# TianShu 一键启动环境变量
# 编辑后下次启动自动加载

# 设置为 1 跳过认证 (开发模式)
TIAN_SHU_AUTH_DISABLED=0
"@ | Out-File -FilePath $EnvFile -Encoding utf8
    }
    # 加载环境变量
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#')) {
            $parts = $line -split '=', 2
            if ($parts.Length -eq 2) {
                $name = $parts[0].Trim()
                $value = $parts[1].Trim()
                Set-Item -Path "Env:$name" -Value $value
            }
        }
    }
}

function Start-Backend {
    Write-Step "Starting backend on port $BackendPort ..."

    if (Test-PortListening $BackendPort) {
        Write-Warn "Port $BackendPort already in use, killing old process"
        Kill-Port $BackendPort
        Start-Sleep -Seconds 2
    }

    Ensure-Venv

    $env:PYTHONPATH = "$Backend;$Backend\packages\harness"
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONUTF8 = "1"

    if ($NoAuth) {
        $env:TIAN_SHU_AUTH_DISABLED = "1"
        Write-Ok "Authentication disabled (dev mode)"
    }

    # 启动后端 (后台, 输出到日志)
    # 注意: Windows 上 psycopg 3 不兼容 ProactorEventLoop,
    #       需要在 uvicorn 启动前 monkey-patch asyncio 使用 SelectorEventLoop。
    $bootScript = @"
import asyncio
import selectors
import sys

# uvicorn hardcodes ProactorEventLoop on Windows for asyncio backend,
# but psycopg 3 cannot use ProactorEventLoop in async mode. Monkey-patch
# uvicorn so its get_loop_factory returns a SelectorEventLoop factory.
import uvicorn
import uvicorn.config as _uv_config

def _selector_loop_factory():
    return asyncio.SelectorEventLoop(selectors.SelectSelector())

# Replace get_loop_factory so it always returns our Selector factory,
# bypassing the auto/asyncio/uvloop selection.
_uv_config.Config.get_loop_factory = lambda self: _selector_loop_factory

# Also patch the default asyncio event loop policy for any code paths
# that call asyncio.get_event_loop() / new_event_loop() directly.
def _selector_new_event_loop(self, *args, **kwargs):
    return asyncio.SelectorEventLoop(selectors.SelectSelector())

asyncio.events.BaseDefaultEventLoopPolicy.new_event_loop = _selector_new_event_loop

uvicorn.run(
    'app.gateway.app:app',
    host='127.0.0.1',
    port=$BackendPort,
    log_level='info',
)
"@
    $bootFile = Join-Path $LogsDir "_boot_backend.py"
    $bootScript | Out-File -FilePath $bootFile -Encoding utf8

    $args = @($bootFile)

    $proc = Start-Process `
        -FilePath $VenvPython `
        -ArgumentList $args `
        -WorkingDirectory $Backend `
        -RedirectStandardOutput $BackendLogOut `
        -RedirectStandardError $BackendLogErr `
        -WindowStyle Hidden `
        -PassThru

    $proc.Id | Out-File -FilePath $BackendPidFile -Encoding ascii
    Write-Ok "Backend started (PID=$($proc.Id))"

    # 等待后端就绪
    Write-Step "Waiting for backend to be ready ..."
    $ready = $false
    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/api/features" `
                -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($r.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            # 还没起来, 继续等待
        }
    }

    if ($ready) {
        Write-Ok "Backend ready (http://127.0.0.1:$BackendPort)"
    } else {
        Write-Err "Backend failed to start within 30 seconds"
        Write-Host "  Check logs: $BackendLogErr"
        throw "Backend startup timeout"
    }
}

function Start-Frontend {
    Write-Step "Starting frontend on port $FrontendPort ..."

    if (Test-PortListening $FrontendPort) {
        Write-Warn "Port $FrontendPort already in use, killing old process"
        Kill-Port $FrontendPort
        Start-Sleep -Seconds 2
    }

    Ensure-FrontendDeps

    # 前端必须指向我们的后端
    $env:TIANSHU_BACKEND_URL = "http://127.0.0.1:$BackendPort"

    # 启动前端 (后台, 输出到日志)
    $pnpmScript = Join-Path $Root "scripts\pnpm.py"

    $proc = Start-Process `
        -FilePath "python" `
        -ArgumentList @($pnpmScript, "dev") `
        -WorkingDirectory $Frontend `
        -RedirectStandardOutput $FrontendLogOut `
        -RedirectStandardError $FrontendLogErr `
        -WindowStyle Hidden `
        -PassThru

    $proc.Id | Out-File -FilePath $FrontendPidFile -Encoding ascii
    Write-Ok "Frontend started (PID=$($proc.Id))"

    # 等待前端就绪
    Write-Step "Waiting for frontend to be ready ..."
    $ready = $false
    for ($i = 1; $i -le 60; $i++) {
        Start-Sleep -Seconds 1
        if (Test-PortListening $FrontendPort) {
            # 端口起来了, 但还要确认返回有效页面
            try {
                $r = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort" `
                    -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
                if ($r.StatusCode -in @(200, 307)) {
                    $ready = $true
                    break
                }
            } catch {
                # 还没编译完, 继续等
            }
        }
    }

    if ($ready) {
        Write-Ok "Frontend ready (http://localhost:$FrontendPort)"
    } else {
        Write-Warn "Frontend not fully ready in 60s, but may still be compiling"
        Write-Host "  Check logs: $FrontendLogErr"
    }
}

function Seed-Data {
    Write-Step "Seeding test agents and workflows ..."

    # Write seed.py to a temp file using single-quoted here-string (no PowerShell
    # variable interpolation) and substitute the backend port via .Replace().
    $tmpScript = Join-Path $LogsDir "seed.py"
    Ensure-Dir (Split-Path $tmpScript)

@'
"""Seed test data into TianShu backend (PostgreSQL)."""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:__BACKEND_PORT__"
TIMEOUT = 15

ok = True


def http_get(path):
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def http_post(path, payload, name):
    global ok
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            print(f"  OK Created {name}")
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 409:
            print(f"  - {name} already exists")
            return None
        body = e.read().decode("utf-8", errors="ignore")
        print(f"  X {name}: HTTP {e.code} - {body[:120]}")
        ok = False
        return None
    except Exception as e:
        print(f"  X {name}: {e}")
        ok = False
        return None


# ---------- 1) User models ----------
# Models are no longer hardcoded in config.yaml -- each user owns their
# own rows in the ``user_models`` table. Register two demo rows here
# so the rest of the seed can attach agents to them.
model_defs = [
    {
        "name": "minimax-m3",
        "display_name": "MiniMax M3 (CN)",
        "provider": "MiniMax",
        "api_key": "${MINIMAX_API_KEY}",
        "base_url": "https://api.minimaxi.com/v1",
        "model": "MiniMax-M3",
        "parameters": {
            "request_timeout": 600.0,
            "max_retries": 2,
            "max_tokens": 4096,
            "temperature": 1.0,
        },
        "supports_thinking": True,
        "supports_reasoning_effort": False,
    },
    {
        "name": "deepseek-v4-Flash",
        "display_name": "DeepSeek V4 Flash",
        "provider": "deepseek",
        "api_key": "${DEEPSEEK_API_KEY}",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-v4-flash",
        "parameters": {
            "timeout": 600.0,
            "max_retries": 2,
            "max_tokens": 8192,
        },
        "supports_thinking": True,
        "supports_reasoning_effort": False,
    },
]

# Substitute env vars lazily -- prefer real values, fall back to a
# placeholder so the request still goes through (the model will not
# work without a real key, but it shows up in the selector).
import os

def _resolve_env(value):
    if not isinstance(value, str):
        return value
    if value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        return os.environ.get(env_name, f"placeholder-{env_name.lower()}")
    return value

for m in model_defs:
    m["api_key"] = _resolve_env(m["api_key"])

existing_models = http_get("/api/user/models").get("models", [])
existing_model_names = {m["name"] for m in existing_models}
for m in model_defs:
    if m["name"] in existing_model_names:
        print(f"  - user_model:{m['name']} already exists")
        continue
    http_post("/api/user/models", m, f"user_model:{m['name']}")

# ---------- 2) Agents ----------
agent_defs = [
    {
        "name": "researcher",
        "description": "市场调研员 - 搜集和分析数据",
        "model": "minimax-m3",
        "soul": "你是一个专业的市场调研员。你的任务是搜集数据、分析趋势，并输出结构化的调研报告。\n\n工作准则：\n1. 基于输入数据进行客观分析\n2. 提供数据支持的观点\n3. 输出结构化的分析结果",
    },
    {
        "name": "analyst",
        "description": "数据分析师 - 深度分析和洞察",
        "model": "deepseek-v4-Flash",
        "soul": "你是一个资深数据分析师。你接收调研数据，进行深度分析，发现潜在规律和机会。\n\n工作准则：\n1. 对输入数据进行多维度分析\n2. 识别关键趋势和异常\n3. 提供可执行的洞察建议",
    },
    {
        "name": "writer",
        "description": "报告撰写员 - 生成专业报告",
        "model": "minimax-m3",
        "soul": "你是一个专业的报告撰写员。你接收分析结果，将其转化为清晰、专业的报告文档。\n\n工作准则：\n1. 结构清晰：摘要、正文、结论\n2. 语言专业但易懂\n3. 包含关键数据和建议",
    },
]

agents = http_get("/api/agents").get("agents", [])
existing_names = {a["name"] for a in agents}
for a in agent_defs:
    if a["name"] in existing_names:
        print(f"  - agent:{a['name']} already exists")
        continue
    http_post("/api/agents", a, f"agent:{a['name']}")

# ---------- 2) Workflow ----------
wfs = http_get("/api/workflows").get("workflows", [])
if any(w["name"] == "Multi-Agent Analysis Pipeline" for w in wfs):
    print("  - workflow:Multi-Agent Analysis Pipeline already exists")
else:
    wf_def = {
        "name": "Multi-Agent Analysis Pipeline",
        "description": "调研员 -> 分析师 -> 输出报告",
        "definition": {
            "nodes": [
                {
                    "id": "input_1",
                    "type": "input",
                    "name": "用户输入",
                    "config": {"input_key": "message", "default_value": ""},
                    "input_mapping": {},
                    "position": {"x": 100, "y": 200},
                },
                {
                    "id": "agent_researcher",
                    "type": "agent",
                    "name": "调研员",
                    "config": {
                        "agent_name": "researcher",
                        "model": "minimax-m3",
                        "system_prompt": "你是一个专业的市场调研员。",
                        "timeout": 60,
                    },
                    "input_mapping": {},
                    "position": {"x": 350, "y": 200},
                },
                {
                    "id": "agent_analyst",
                    "type": "agent",
                    "name": "分析师",
                    "config": {
                        "agent_name": "analyst",
                        "model": "deepseek-v4-Flash",
                        "system_prompt": "你是一个资深数据分析师。",
                        "timeout": 60,
                    },
                    "input_mapping": {},
                    "position": {"x": 600, "y": 200},
                },
                {
                    "id": "output_1",
                    "type": "output",
                    "name": "最终报告",
                    "config": {"aggregation": "merge"},
                    "input_mapping": {},
                    "position": {"x": 850, "y": 200},
                },
            ],
            "edges": [
                {"id": "e1", "source": "input_1", "target": "agent_researcher"},
                {"id": "e2", "source": "agent_researcher", "target": "agent_analyst"},
                {"id": "e3", "source": "agent_analyst", "target": "output_1"},
            ],
        },
        "input_schema": {"type": "object"},
        "is_template": False,
    }
    http_post("/api/workflows", wf_def, "workflow:Multi-Agent Analysis Pipeline")

sys.exit(0 if ok else 1)
'@ -replace '__BACKEND_PORT__', $BackendPort | Out-File -FilePath $tmpScript -Encoding utf8

    try {
        & $VenvPython $tmpScript
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Seed complete"
        } else {
            Write-Warn "Some seed operations failed (see output above)"
        }
    } finally {
        Remove-Item $tmpScript -Force -ErrorAction SilentlyContinue
    }
}

function Show-Status {
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  TianShu 服务状态" -ForegroundColor Cyan
    Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host ""

    $backendProc = Read-PidFile $BackendPidFile
    $backendPortOpen = Test-PortListening $BackendPort
    $frontendProc = Read-PidFile $FrontendPidFile
    $frontendPortOpen = Test-PortListening $FrontendPort

    if ($backendProc -or $backendPortOpen) {
        Write-Host "  ✓ Backend   : " -NoNewline -ForegroundColor Green
        Write-Host "running " -NoNewline
        if ($backendProc) { Write-Host "(PID $($backendProc.Id)) " -NoNewline -ForegroundColor Gray }
        Write-Host "→ http://127.0.0.1:$BackendPort"
        Write-Host "    logs: $BackendLogOut / $BackendLogErr" -ForegroundColor DarkGray
    } else {
        Write-Host "  ✗ Backend   : not running" -ForegroundColor Red
    }

    if ($frontendProc -or $frontendPortOpen) {
        Write-Host "  ✓ Frontend  : " -NoNewline -ForegroundColor Green
        Write-Host "running " -NoNewline
        if ($frontendProc) { Write-Host "(PID $($frontendProc.Id)) " -NoNewline -ForegroundColor Gray }
        Write-Host "→ http://localhost:$FrontendPort"
        Write-Host "    logs: $FrontendLogOut / $FrontendLogErr" -ForegroundColor DarkGray
    } else {
        Write-Host "  ✗ Frontend  : not running" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "  配置文件: $Root\config.yaml" -ForegroundColor DarkGray
    Write-Host ""
}

function Stop-All {
    Write-Step "Stopping all services ..."
    $killed = $false

    $frontendProc = Read-PidFile $FrontendPidFile
    if ($frontendProc) {
        try {
            Stop-Process -Id $frontendProc.Id -Force -ErrorAction Stop
            Write-Ok "Stopped frontend (PID=$($frontendProc.Id))"
            $killed = $true
        } catch {
            Write-Warn "Frontend PID=$($frontendProc.Id) already gone"
        }
        Remove-Item $FrontendPidFile -Force -ErrorAction SilentlyContinue
    }

    $backendProc = Read-PidFile $BackendPidFile
    if ($backendProc) {
        try {
            Stop-Process -Id $backendProc.Id -Force -ErrorAction Stop
            Write-Ok "Stopped backend (PID=$($backendProc.Id))"
            $killed = $true
        } catch {
            Write-Warn "Backend PID=$($backendProc.Id) already gone"
        }
        Remove-Item $BackendPidFile -Force -ErrorAction SilentlyContinue
    }

    Kill-Port $FrontendPort
    Kill-Port $BackendPort

    if (-not $killed) {
        Write-Warn "No tracked processes found"
    }
}

# ============================================================================
# 主流程
# ============================================================================
Ensure-Dir $LogsDir

if ($Stop) {
    Stop-All
    exit 0
}

if ($Status) {
    Show-Status
    exit 0
}

if ($Restart) {
    Stop-All
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  TianShu 一键启动" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Ensure-EnvFile
Ensure-Config

# 启动
Start-Backend
Start-Frontend

if ($Seed) {
    Seed-Data
}

Show-Status
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ✓ TianShu 启动完成" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "  访问地址:"
Write-Host "    前端:    http://localhost:$FrontendPort" -ForegroundColor White
Write-Host "    工作流:  http://localhost:$FrontendPort/workspace/workflows" -ForegroundColor White
Write-Host "    智能体:  http://localhost:$FrontendPort/workspace/agents" -ForegroundColor White
Write-Host "    聊天:    http://localhost:$FrontendPort/workspace/chats/new" -ForegroundColor White
Write-Host ""
Write-Host "  停止服务:  .\quick-start.ps1 -Stop" -ForegroundColor DarkGray
Write-Host "  查看状态:  .\quick-start.ps1 -Status" -ForegroundColor DarkGray
Write-Host "  重启服务:  .\quick-start.ps1 -Restart" -ForegroundColor DarkGray
Write-Host "  停止认证:  .\quick-start.ps1 -NoAuth   (开发模式,跳过登录)" -ForegroundColor DarkGray
Write-Host ""