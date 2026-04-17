# my-vue-app 前端说明

## 1. 项目简介

这是一个面向 SMT 问答系统的前端项目，采用前后端分离方式开发，主要提供：

- 登录 / 注册页面
- 问答会话页面
- 历史会话管理
- 系统求解结果展示
- 代码优化结果展示与对比
- 管理员后台页面
- SMT 基础知识与当前 SMT 输出展示

当前项目整体风格以浅灰色系为主，界面参考聊天类应用，但并非 ChatGPT 的直接复刻。

## 2. 技术栈

- Vue 3
- Vite
- JavaScript
- Axios
- Element Plus
- CSS

## 3. 运行环境

建议环境：

- Node.js 16+
- npm 8+

## 4. 项目结构

```text
my-vue-app
├── public
├── src
│   ├── assets
│   ├── components
│   │   └── AdminPage.vue
│   ├── data
│   │   └── smtGlossary.js
│   ├── App.vue
│   ├── main.js
│   └── style.css
├── axiosInstance.js
├── index.html
├── package.json
└── vite.config.js
```

说明：

- `App.vue` 是当前前端主页面核心文件，包含登录页、聊天页、优化记录相关逻辑
- `AdminPage.vue` 是后台管理页面
- `style.css` 是全局样式文件，包含登录页、聊天页、后台页的大部分样式
- `axiosInstance.js` 是统一的 Axios 实例配置
- `smtGlossary.js` 用于展示 SMT 基础知识

## 5. 主要依赖

`package.json` 当前主要依赖如下：

- `vue`
- `axios`
- `element-plus`
- `vite`
- `@vitejs/plugin-vue`
- `unplugin-auto-import`

## 6. 安装依赖

在项目根目录执行：

```bash
npm install
```

## 7. 启动项目

开发环境启动：

```bash
npm run dev
```

生产环境构建：

```bash
npm run build
```

本地预览构建结果：

```bash
npm run preview
```

## 8. 前后端联调配置

当前 Axios 配置文件：

```text
axiosInstance.js
```

当前基础配置为：

```js
import axios from 'axios'

const API = axios.create({
  baseURL: 'http://localhost:8080',
  timeout: 30000,
})

export default API
```

说明：

- 当前前端默认请求后端地址为 `http://localhost:8080`
- 请求超时时间为 `30000ms`

## 9. 页面功能说明

## 9.1 登录 / 注册页面

登录注册页支持：

- 登录
- 注册
- 登录失败提示
- 注册格式校验

当前特点：

- 登录页采用灰色系风格
- 登录后会保存当前用户信息到 `localStorage`

## 9.2 会话页面

会话页面主要包括：

- 左侧历史记录区
- 中间聊天区
- 页面下方的 SMT 参考区

支持功能：

- 新建会话
- 查看历史会话
- 删除会话
- 输入自然语言问题并发送给后端
- 展示用户问题与系统回复
- 展示当前 SMT 输出
- 复制代码

## 9.3 优化相关功能

对于系统回复，前端支持：

- 点击“优化”按钮调用后端 `/optimizeCode`
- 自动查询某条系统回复对应的优化记录
- 将优化结果作为新的“后端优化结果”消息展示在聊天区
- 点击“对比”按钮查看当前优化记录的原始代码和优化代码
- 删除某条优化记录

当前对比弹窗支持：

- 右侧抽屉显示
- 左右两栏代码对比
- 可拖拽调整抽屉宽度

## 9.4 管理员后台页面

当登录用户 `userType = 1` 时，前端会显示“管理”入口，并可跳转后台管理页面。

后台管理页面当前包含三部分：

- 用户信息管理
- 会话数据管理
- 历史记录维护

支持功能：

- 查询全部用户
- 删除用户
- 查询全部会话
- 删除会话
- 查询全部优化记录
- 删除优化记录
- 查看优化记录代码详情

## 10. 当前前端接口清单

前端当前已接入的后端接口主要包括：

### 用户相关

- `POST /login`
- `POST /register`
- `POST /updatePassword`
- `GET /users`
- `POST /deleteUser`

### 会话相关

- `GET /sessions`
- `GET /allSessions`
- `GET /messages`
- `POST /session`
- `POST /send`
- `POST /delete`

### 优化记录相关

- `GET /optimizeRecords`
- `GET /optimizeRecords/byMessage`
- `POST /optimizeCode`
- `POST /deleteOptimizeRecord`

## 11. 路由说明

当前项目没有引入 `vue-router`，而是直接在 `App.vue` 中基于浏览器地址进行简单页面切换。

当前主要页面状态：

- `/`：聊天页
- `/admin`：管理员后台页

说明：

- 页面切换通过 `window.history.pushState` 实现
- 登录状态与用户信息通过 `localStorage` 恢复

## 12. 关键文件说明

### `src/App.vue`

主要负责：

- 登录 / 注册逻辑
- 用户信息持久化
- 聊天会话逻辑
- 会话消息渲染
- 优化消息渲染
- SMT 输出展示
- 代码对比抽屉逻辑

### `src/components/AdminPage.vue`

主要负责：

- 管理员后台页面布局
- 用户、会话、优化记录表格展示
- 刷新、删除、详情查看等后台管理操作

### `src/style.css`

主要负责：

- 全局页面样式
- 登录页样式
- 聊天页布局与消息样式
- 管理页面样式
- 抽屉、弹窗、底部参考区样式

## 13. 当前实现特点

- 使用 Vue 3 单文件组件开发
- 主逻辑集中在 `App.vue`
- 使用 Element Plus 组件库辅助后台页面和抽屉展示
- 已支持管理员与普通用户区分
- 已支持长文本、代码展示、复制和优化对比
- 已支持通过页面滚动查看下方 SMT 参考区

## 14. 开发建议

后续如果继续扩展，建议优先做以下优化：

- 引入 `vue-router` 规范页面路由管理
- 将 `App.vue` 中的大块逻辑拆分成多个组件
- 将接口地址统一抽离到单独配置文件
- 增加请求拦截器和统一错误处理
- 增加类型约束，可考虑迁移到 TypeScript
- 对聊天消息、优化记录、用户信息建立独立状态管理

## 15. 前后端项目路径

前端项目：

```text
D:\software\codex\file\lzw\vueProject\my-vue-app
```

后端项目：

```text
D:\software\codex\file\lzw\springboot02
```

## 16. 备注

当前项目已经具备完整的前后端联调基础，适合继续扩展为：

- SMT 问答系统
- 形式化验证辅助平台
- 代码优化与历史追踪系统
