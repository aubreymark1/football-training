# 岭足体能训练

基于 Flask 和 SQLite 的球队训练记录网站，支持任务、训练打卡、积分、球队管理、邮箱验证和账号找回。

运行前安装 `requirements.txt` 中的依赖，并配置安全的 `TEAM_SECRET`。生产部署示例见 `deploy/`。邮件功能需要在服务器环境中配置 `TEAM_SMTP_USER`、`TEAM_SMTP_PASSWORD` 和 `TEAM_SMTP_FROM`，不要将真实配置提交到仓库。

出于隐私考虑，实际数据库、训练图片、球队问答语料及服务器连接资料不包含在仓库中。缺少问答语料时，相关检索功能和依赖该语料的测试不可用。

新注册队员从加入当周开始承担必做任务，不追扣加入前的周；历史账号的入队日期需要管理员核实并在成员管理中填写；确认前只结算升级当周及之后的任务，确认后会核对入队前的既有扣分。

本地测试：`python -m unittest test_app`。初始化管理员：`python app.py init-admin --name 管理员昵称`；启动开发服务器：`python app.py serve`。
