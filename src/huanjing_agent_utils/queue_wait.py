"""Allow-listed observations of the existing Worker's queue admission decision."""
from __future__ import annotations

import json
import math
import time

WAIT_REASONS = frozenset({
    "RESOURCE_BUDGET_UNKNOWN", "GPU_OBSERVATION_UNAVAILABLE", "GPU_THERMAL_HEADROOM_INSUFFICIENT",
    "MODEL_EXCEEDS_GPU_CAPACITY", "RAM_OBSERVATION_UNAVAILABLE", "SYSTEM_RAM_HEADROOM_INSUFFICIENT",
    "SERIAL_ONLY_WITH_ACTIVE_RESOURCE",
    "GLOBAL_FIFO_PREDECESSOR", "GLOBAL_FIFO_ACTIVE_TASK", "GLOBAL_FIFO_RECOVERY_HOLD",
    "NATIVE_COMFY_EXCLUSIVE", "H3_STAGED_RUNTIME_UNAVAILABLE", "H3_SECONDARY_GPU_UNAVAILABLE",
})
WAIT_NUMBERS = {
    "available_ram_mib": (0, 1048576), "required_ram_mib": (0, 1048576),
    "gpu_index": (0, 64), "free_vram_mib": (0, 1048576),
    "required_vram_mib": (0, 1048576), "total_vram_mib": (0, 1048576),
    "temperature_c": (-40, 150), "max_admission_temperature_c": (0, 150),
}


def normalize_queue_wait(value, *, now=None):
    if not isinstance(value, dict) or value.get("source") != "WORKER_SCHEDULER" or value.get("reason_code") not in WAIT_REASONS:
        return None
    checked = value.get("checked_at")
    current = time.time() if now is None else now
    if type(checked) not in (int, float) or not math.isfinite(checked) or not -5 <= current - checked <= 45:
        return None
    result = {"source": "WORKER_SCHEDULER", "reason_code": value["reason_code"], "checked_at": checked}
    for key, (minimum, maximum) in WAIT_NUMBERS.items():
        if key in value:
            number = value[key]
            if type(number) is not int or not minimum <= number <= maximum:
                return None
            result[key] = number
    return result


def project_queue_wait(job):
    if job.get("status") not in {"DISPATCHING", "RUNNING"} or job.get("stage") != "QUEUED":
        return None, None
    try:
        wait = normalize_queue_wait(json.loads(job.get("queue_wait_json") or "{}"))
    except (TypeError, ValueError):
        wait = None
    if wait is None:
        return None, None
    reason = wait["reason_code"]
    messages = {
        "GLOBAL_FIFO_PREDECESSOR": "等待前面的任务完成交付。",
        "GLOBAL_FIFO_ACTIVE_TASK": "当前任务的另一阶段正在执行，等待其结束。",
        "GLOBAL_FIFO_RECOVERY_HOLD": "原任务结果尚未核定，队列保留等待恢复。",
        "RESOURCE_BUDGET_UNKNOWN": "资源预算尚未确认，任务正在等待调度。",
        "GPU_OBSERVATION_UNAVAILABLE": "显卡状态暂时无法读取，任务正在等待调度。",
        "GPU_THERMAL_HEADROOM_INSUFFICIENT": "显卡温度尚未满足当前调度条件，任务正在等待。",
        "MODEL_EXCEEDS_GPU_CAPACITY": "模型所需显存超过当前显卡容量，请选择更小模型或取消此任务。",
        "RAM_OBSERVATION_UNAVAILABLE": "系统内存状态暂时无法读取，任务正在等待调度。",
        "SYSTEM_RAM_HEADROOM_INSUFFICIENT": "系统可用内存不足，任务仍在排队，尚未开始生成。",
        "SERIAL_ONLY_WITH_ACTIVE_RESOURCE": "另一个生成任务正在使用所需资源，本任务按顺序等待。",
        "NATIVE_COMFY_EXCLUSIVE": "画布中的工作流正在使用显卡，本任务将在资源释放后继续。",
        "H3_STAGED_RUNTIME_UNAVAILABLE": "视频分阶段服务尚未就绪，任务保留在原队列，服务恢复后继续。",
        "H3_SECONDARY_GPU_UNAVAILABLE": "视频需要的第二张显卡暂不可用或余量不足，任务将在资源就绪后继续。",
    }
    message = messages[reason]
    if reason.startswith("GLOBAL_FIFO_"):
        position = job.get("queue_position")
        # This counts unfinished root tickets, including this task; it is
        # not a count of running jobs. Child stages retain the root ticket.
        prefix = f"全局队列第 {position} 位，" if type(position) is int and 1 <= position <= 100_000 else "全局队列按提交顺序等待，"
        message = prefix + message
    if reason == "SYSTEM_RAM_HEADROOM_INSUFFICIENT" and all(key in wait for key in ("available_ram_mib", "required_ram_mib")):
        message += f"当前可用 {wait['available_ram_mib'] / 1024:.1f} GiB，需要 {wait['required_ram_mib'] / 1024:.1f} GiB（含运行余量）。"
    if reason == "SYSTEM_RAM_HEADROOM_INSUFFICIENT":
        message += "关闭暂不用的占内存程序后会自动重试，也可取消任务。"
    return wait, message
