# 幻境智能体工具集

从「幻境智能体／云笙」现有代码中整理的两个Python小工具：队列等待信息投影和分页游标校验。面向需要展示后台任务状态、实现会话列表分页的开发者。

这是独立组件的首次发布候选，范围很小，不包含完整AI助手、模型、GPU执行器或云服务。尚无经核实的外部采用或下载量。

## 包含什么

- queue_wait：限制可展示的等待原因、观测字段、数值范围和时间窗口，将有效队列观测投影为中文等待说明。
- history_pagination：生成和检查范围绑定的分页位置游标，检查规范编码、字段、标识符及有效期。

这两个模块只使用Python标准库。分页模块所需的两个异常基类已一并整理到本包，不再导入原项目。

## 在源码目录使用

要求Python 3.10或更新版本。在本目录打开终端：

~~~powershell
$env:PYTHONPATH = 'src'
python -B -m unittest discover -s tests -v
~~~

队列观测校验示例：

~~~python
from huanjing_agent_utils.queue_wait import normalize_queue_wait

result = normalize_queue_wait({
    'source': 'WORKER_SCHEDULER',
    'reason_code': 'GLOBAL_FIFO_PREDECESSOR',
    'checked_at': 1000,
    'private_prompt': '不会进入展示结果',
}, now=1001)
assert result == {
    'source': 'WORKER_SCHEDULER',
    'reason_code': 'GLOBAL_FIFO_PREDECESSOR',
    'checked_at': 1000,
}
~~~

分页游标示例：

~~~python
from huanjing_agent_utils.history_pagination import binding, decode, encode, page_filters

filters = page_filters(
    {'q': '', 'sort': 'UPDATED_DESC'},
    page_size=20, date_from='', date_to='',
)
scope = binding('demo-user', filters)
cursor = encode(
    {'session_id': 'demo-session', 'updated_at': '2026-10-21T00:00:00+00:00'},
    filters, scope, now=1000, token=None,
)
position = decode(cursor, scope, now=1001)
assert position['after']['id'] == 'demo-session'
~~~

## 使用边界

队列工具只校验和展示输入，不执行任务、不测量资源、不控制GPU，也不设置内存余量。source字段不是身份凭据，调用方必须自行保证观测来源可信。时间窗口不等于网络状态或资源测量准确性。

分页游标是位置，不是权限、签名、加密或访问令牌。binding是普通摘要，不能用它代替服务端身份认证、owner查询条件或数据权限检查。调用方仍需验证允许的排序与查询字段；本组件不执行SQL、不提供数据库历史快照。

本包的合成测试只覆盖这两个独立模块，不代表云笙完整系统、真实GPU业务或云端发布已经通过验收。

## 维护与来源

主要维护者：[@missgeng95-jpg](https://github.com/missgeng95-jpg)。职责见MAINTAINERS.md。整理来源和最小改动见SOURCES.md。

欢迎提交可以复现的问题和具体改进。请勿在Issue中粘贴密钥、私人对话、用户数据或生产日志。

## 许可状态

本工具集使用MIT许可证，见LICENSE。此许可仅覆盖本仓库实际发布的组件与文档，不代表完整云笙项目或其模型、素材、作品获得相同授权。
