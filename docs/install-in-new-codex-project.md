# Install In A New Codex Project

## 目标

在新的 Codex 项目中使用本 Skill 时，Skill 引擎安装在全局目录，账号数据保存在新项目本地目录。

不要把新项目的账号档案、对标帖子和规则卡片写回全局 Skill 安装目录。

## 1. 确认 Skill 已安装

全局安装目录应存在：

```text
~/.codex/skills/xhs-personal-content-skill/
```

如果已经复制过，重启 Codex 后即可在新项目中通过关键词触发。

安装 Python 依赖：

```bash
cd ~/.codex/skills/xhs-personal-content-skill
python3 -m pip install -r requirements.txt
```

## 2. 在新项目中触发 Skill

在新的 Codex 项目中直接说：

```text
小红书账号运营，初始化这个项目的账号工作区
```

推荐项目本地工作区：

```text
.xhs-personal-content-skill/real-sample/
```

## 3. 补充账号档案

直接用自然语言告诉 Codex：

```text
小红书账号运营，账号名是 XXXXXXX，定位是……，目标用户是……，风格要干货、接地气、有结果感，不要太 AI、太营销、太标题党。
```

Codex 应自动写入：

```text
.xhs-personal-content-skill/real-sample/creator_profile.json
```

## 4. 添加对标账号和对标帖子

可以发送截图、链接或复制文本：

```text
小红书账号运营，分析这个截图，加入对标库
```

Codex 应自动写入：

```text
.xhs-personal-content-skill/real-sample/benchmark_account.json
.xhs-personal-content-skill/real-sample/benchmark_post.json
```

如果要让 Skill 读取用户授权浏览器中的单个链接当前可见内容，先启动专用 Chrome：

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.xhs-personal-content-skill/chrome-profile"
```

首次使用时，在这个专用 Chrome 中自行登录小红书。Skill 只连接这个调试浏览器读取用户提交的单个链接，不读取日常 Chrome Profile，不批量抓取，不绕过登录、验证码或风控。

## 5. 运行验证

Codex 应从 Skill 引擎目录运行：

```bash
cd ~/.codex/skills/xhs-personal-content-skill
python3 -m app.cli validate-real-sample --workspace /absolute/path/to/new-project/.xhs-personal-content-skill/real-sample
```

报告会写入新项目：

```text
.xhs-personal-content-skill/real-sample/reports/validation_report.md
.xhs-personal-content-skill/real-sample/reports/human_review_form.md
```

## 6. 持续调教方式

持续输入：

- 对标账号
- 对标帖子
- 用户偏好
- 不喜欢的表达
- 已发布内容数据
- 人工评价

长期沉淀：

- 标签
- 规则卡片
- 选题池
- 草稿
- 发布任务
- 复盘记录

这才是让 Skill 越来越贴合个人账号的关键。
