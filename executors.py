#!/usr/bin/env python3
"""小希-Mesh 执行器框架

每个智能体的执行器，用于真正执行收到的调用请求。
执行器接收params，返回执行结果。
"""
import asyncio
import json
import logging
import os
import shlex
import subprocess
from typing import Any, Callable, Awaitable, Optional


log = logging.getLogger("xiaoxi-mesh.executors")

BASE_DIR = "/home/caowei/xiaoxi-project"

# 安全的文件路径校验
def _safe_path(path: str, base_dir: str = BASE_DIR) -> str:
    """将路径限制在指定目录内"""
    real_path = os.path.realpath(os.path.join(base_dir, path))
    real_base = os.path.realpath(base_dir)
    if not real_path.startswith(real_base + "/") and real_path != real_base:
        raise ValueError(f"路径越权: {path}")
    return real_path


# ── 通用执行器 ──

async def hermes_call(params: dict) -> dict:
    """调用本地Hermes"""
    prompt = params.get("prompt", "")
    timeout = params.get("timeout", 300)
    
    if not prompt:
        return {"success": False, "error": "prompt为空"}
    
    try:
        # 使用hermes CLI调用
        cmd = ["hermes", "--yolo", "-z", prompt]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        
        output = stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0:
            return {"success": True, "result": output}
        else:
            error = stderr.decode("utf-8", errors="replace").strip()
            return {"success": False, "error": error or "执行失败", "output": output}
    except asyncio.TimeoutError:
        return {"success": False, "error": f"超时({timeout}s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def script_exec(params: dict) -> dict:
    """执行脚本"""
    script = params.get("script", "")
    timeout = params.get("timeout", 60)

    if not script:
        return {"success": False, "error": "script为空"}

    # 安全限制
    if len(script) > 4096:
        return {"success": False, "error": "脚本过长"}

    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        output = stdout.decode("utf-8", errors="replace").strip()
        error = stderr.decode("utf-8", errors="replace").strip()

        return {
            "success": proc.returncode == 0,
            "output": output,
            "error": error if error else None,
            "exit_code": proc.returncode,
        }
    except asyncio.TimeoutError:
        return {"success": False, "error": f"超时({timeout}s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def system_monitor(params: dict) -> dict:
    """系统监控"""
    try:
        result = {}
        
        # CPU使用率
        with open("/proc/stat") as f:
            line = f.readline()
            values = [int(x) for x in line.split()[1:]]
            idle = values[3]
            total = sum(values)
            result["cpu"] = {"idle": idle, "total": total}
        
        # 内存
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    result["memory_total"] = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable"):
                    result["memory_available"] = int(line.split()[1]) * 1024
        
        # 磁盘
        st = os.statvfs("/")
        result["disk_total"] = st.f_blocks * st.f_frsize
        result["disk_free"] = st.f_bavail * st.f_frsize
        
        # Uptime
        with open("/proc/uptime") as f:
            result["uptime"] = float(f.readline().split()[0])
        
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def file_ops(params: dict) -> dict:
    """文件操作"""
    action = params.get("action", "read")
    path = params.get("path", "")
    content = params.get("content", "")

    try:
        # 路径安全校验
        safe_path = _safe_path(path, BASE_DIR)

        if action == "read":
            with open(safe_path, "r") as f:
                return {"success": True, "result": f.read()}

        elif action == "write":
            os.makedirs(os.path.dirname(safe_path) or ".", exist_ok=True)
            with open(safe_path, "w") as f:
                f.write(content)
            return {"success": True, "result": f"已写入 {len(content)} 字节"}

        elif action == "list":
            files = os.listdir(safe_path) if path else os.listdir(".")
            return {"success": True, "result": files}

        elif action == "exists":
            return {"success": True, "result": os.path.exists(safe_path)}

        else:
            return {"success": False, "error": f"未知操作: {action}"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def github_push(params: dict) -> dict:
    """GitHub推送操作"""
    action = params.get("action", "push")
    repo_path = params.get("repo_path", "")
    branch = params.get("branch", "main")
    message = params.get("message", "")

    try:
        if not repo_path:
            return {"success": False, "error": "repo_path为空"}

        # 路径安全校验
        safe_repo = _safe_path(repo_path, BASE_DIR)

        if action == "push":
            # 执行git push
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", safe_repo, "push", "origin", branch,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            if proc.returncode == 0:
                return {"success": True, "result": stdout.decode("utf-8").strip()}
            else:
                error = stderr.decode("utf-8").strip()
                return {"success": False, "error": error or "推送失败"}

        elif action == "commit":
            # 执行git add和commit（通过stdin传message防注入）
            if not message:
                return {"success": False, "error": "commit message为空"}

            # git add
            proc_add = await asyncio.create_subprocess_exec(
                "git", "-C", safe_repo, "add", "-A",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc_add.communicate(), timeout=30)
            if proc_add.returncode != 0:
                return {"success": False, "error": "git add 失败"}

            # git commit - 通过stdin传递message防止注入
            proc_commit = await asyncio.create_subprocess_exec(
                "git", "-C", safe_repo, "commit", "-F", "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc_commit.communicate(input=message.encode("utf-8")), timeout=30
            )

            if proc_commit.returncode == 0:
                return {"success": True, "result": stdout.decode("utf-8").strip()}
            else:
                error = stderr.decode("utf-8").strip()
                return {"success": False, "error": error or "提交失败"}

        elif action == "status":
            # 执行git status
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", safe_repo, "status", "--short",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

            return {"success": True, "result": stdout.decode("utf-8").strip()}

        else:
            return {"success": False, "error": f"未知操作: {action}"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except asyncio.TimeoutError:
        return {"success": False, "error": "操作超时"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def web_search(params: dict) -> dict:
    """网络搜索（调用Hermes）"""
    query = params.get("query", "")
    if not query:
        return {"success": False, "error": "query为空"}
    
    return await hermes_call({"prompt": f"搜索: {query}", "timeout": 60})


async def code_generation(params: dict) -> dict:
    """代码生成（调用Hermes）"""
    description = params.get("description", "")
    language = params.get("language", "python")
    
    if not description:
        return {"success": False, "error": "description为空"}
    
    return await hermes_call({
        "prompt": f"用{language}写代码: {description}",
        "timeout": 120,
    })


# ── 小青专属执行器 ──

async def desktop_automation(params: dict) -> dict:
    """桌面自动化"""
    action = params.get("action", "")
    
    if action == "screenshot":
        # 截图
        path = params.get("path", "/tmp/screenshot.png")
        try:
            proc = await asyncio.create_subprocess_exec(
                "gnome-screenshot", "-f", path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return {"success": True, "result": path}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    elif action == "clipboard":
        # 剪贴板操作
        try:
            proc = await asyncio.create_subprocess_exec(
                "xclip", "-selection", "clipboard", "-o",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return {"success": True, "result": stdout.decode("utf-8")}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    else:
        return {"success": False, "error": f"未知操作: {action}"}


async def wechat_operations(params: dict) -> dict:
    """微信操作（通过Hermes）"""
    action = params.get("action", "")
    return await hermes_call({
        "prompt": f"微信操作: {action}",
        "timeout": 60,
    })


# ── 执行器注册表 ──

# 通用执行器（所有智能体都有）
COMMON_EXECUTORS: dict[str, Callable[[dict], Awaitable[dict]]] = {
    "hermes_call": hermes_call,
    "script_exec": script_exec,
    "system_monitor": system_monitor,
    "file_ops": file_ops,
    "web_search": web_search,
    "code_generation": code_generation,
}

# 小青专属执行器
XIAOQING_EXECUTORS = {
    **COMMON_EXECUTORS,
    "desktop_automation": desktop_automation,
    "wechat_operations": wechat_operations,
    "file_transfer": file_ops,  # 文件操作
    "translation": hermes_call,  # 翻译通过Hermes
}

# 小白专属执行器
XIAOBAI_EXECUTORS = {
    **COMMON_EXECUTORS,
    "download_management": script_exec,  # 下载管理通过脚本
    "ssh_operations": script_exec,  # SSH通过脚本
    "github_push": github_push,  # GitHub推送
}

# 小蓝专属执行器
XIAOLAN_EXECUTORS = {
    **COMMON_EXECUTORS,
    "data_analysis": hermes_call,  # 数据分析通过Hermes
    "api_integration": hermes_call,  # API集成通过Hermes
    "task_scheduling": script_exec,  # 任务调度通过脚本
}

# 执行器映射
EXECUTOR_MAP = {
    "xiaoqing": XIAOQING_EXECUTORS,
    "xiaobai": XIAOBAI_EXECUTORS,
    "xiaolan": XIAOLAN_EXECUTORS,
}


def get_executors(agent_id: str) -> dict[str, Callable[[dict], Awaitable[dict]]]:
    """获取指定智能体的执行器"""
    return EXECUTOR_MAP.get(agent_id, COMMON_EXECUTORS)
