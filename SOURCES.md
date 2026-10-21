# 源码来源与整理范围

本包于2026-10-21从维护者的幻境智能体现有工作区整理。下表摘要标识整理时的原始文件字节；它们不是活动审批、外部使用或独立版权审定证明。

| 本包文件 | 原项目相对路径 | 原文件SHA-256 | 整理改动 |
|---|---|---|---|
| src/huanjing_agent_utils/queue_wait.py | agent/execution/queue_wait.py | 629c0e9ef7abd29bd2473615620214420bcb4b4649839905ee3bb9bcfdc1e08c | byte-for-byte unchanged |
| src/huanjing_agent_utils/history_pagination.py | agent/assistant/history_pagination.py | f8531c89910747f85285fdb447052bacc5699094414b3379fd515b360e4c3b80 | exception import redirected to .errors; module description clarified to assign database queries and snapshot consistency to caller; original LF line endings preserved |
| src/huanjing_agent_utils/errors.py | agent/governance/errors.py | 27a42d38c0d890632ce0fd2594fb2e73953299e4c9ee0a511e1ceca23a0b0216 | only GovernanceError and GovernanceValidationError class definitions extracted |

未复制原Git历史、生产配置、运行日志、用户数据、模型或作品。测试为独立合成输入，原项目的整系统与真实业务验收不属于本包验证范围。
