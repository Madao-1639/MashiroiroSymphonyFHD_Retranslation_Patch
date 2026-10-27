# 工具链与调试器操作

只记录**可复用的操作知识**：怎么读内存、怎么下断点、怎么调 32 位导出、怎么避开环境噪声。
具体一次任务的命令见 `script/` 下的脚本 docstring。

## 1. x32dbg 的 MCP 服务

端点 `http://127.0.0.1:50301/mcp`（streamable HTTP），客户端封装在 `tool/x32dbg_mcp.py`。
可用工具（节选，实测）：

| 工具 | 用途 | 关键参数 |
|---|---|---|
| `GetAllModulesFromMemMap` | 模块基址/大小 | — |
| `GetAllRegisters` | 通用寄存器 | — |
| `SetBreakpoint` | 下断（地址或 API 符号） | `target`（**不是** `address`） |
| `ReadDismAtAddress` | 反汇编 | `address`, `byteCount` |
| `FindAllMem` | 按字节模式搜内存（支持 `??` 通配） | `startAddress`, `bytePattern`, `searchSize`, `moduleFilter`（`user`/`system`/`module`） |
| `SearchForStrings` | 按字符串搜内存 | `searchText`, `encodingType`, `startAddress` |
| `run` / `StepInto` / `StepOver` / `StepOut` | 执行控制 | — |

### 1.1 两个必须注意的坑

1. **返回的地址/数值是十进制，但带 `0x` 前缀**。例如模块基址显示 `0x59780000`，
   实际值是十进制 `1501036544`（= `0x59780000`）。解析时按十进制读。
2. **没有「读 N 字节」接口**。`ReadDismAtAddress` 是唯一能取原始字节的途径：
   按绝对地址把每行反汇编的字节列填进字典，缺的字节再从那一个地址补读
   （`tool/x32dbg_mcp.py::read_bytes`）。请求 `byteCount = N` 时会返回覆盖 N 字节的指令，
   长指令会让字节列截断，所以必须按地址回填而不是拼行。

### 1.2 断点策略

- **附加（attach）发生在游戏启动之后时，启动期的函数调用已经过去**，断点不会命中。
  需要截获启动流程时，必须**从调试器启动**目标 exe（停在入口/系统断点后再布点）。
- 目标模块可能每次启动落在不同基址（本作实测 `0x59780000` / `0x5af30000` 都出现过），
  所以不要写死绝对地址：先在 `LoadLibraryW` 上下断，从参数里认出目标模块名，
  `StepOut` 取 `EAX`（模块基址），再按 `base + RVA` 布点。
- 用 ScyllaHide 之类的插件时，注意其「附加模式」不等于「从入口启动」，同样会错过早期调用。

## 2. 调 32 位 DLL 的导出（64 位 Python 下）

`ctypes.WinDLL` 加载 x86 DLL 会报 `[WinError 193] 不是有效的 Win32 应用程序`。
可行做法：用 **32 位 PowerShell**（`C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe`）
+ `Add-Type` 现场编译 C# P/Invoke 包装（.NET Framework 直接产出 x86 程序集），无需编译器。

两个 ctypes 相关的附加坑（同样适用于其它 32 位交互）：

- `GlobalAlloc` / `GlobalLock` 必须声明 `restype = c_void_p`，否则 64 位下句柄被截断成 int32
  （表现为 `access violation writing 0x0`）
- `PostMessageW` / `SendMessageW` 的 `wParam` 要声明为 `c_size_t`，否则长整数报 `OverflowError`

## 3. GUI 程序的无值守驱动

需要「点按钮 + 拖文件进窗口」这类操作时，用 Win32 消息即可，不必引入 UI 自动化框架：

- 找窗口：`EnumWindows` + `GetWindowThreadProcessId` 过滤 pid，`GetWindowTextW` 匹配标题
- 找控件：`EnumChildWindows` + `GetDlgCtrlID`（控件 id 从程序资源/源码里查）
- 点按钮：向控件 `SendMessageW(h, BM_CLICK, 0, 0)`
- 拖放：自己拼 `DROPFILES` 结构（`fWide = 1`）→ `GlobalAlloc` 拷贝 → `PostMessageW(hwnd, WM_DROPFILES, hGlobal, 0)`

进程要**分离启动**（`DETACHED_PROCESS` + 重定向到 `DEVNULL`），否则父进程会一直挂着子进程的句柄，
命令行看起来"卡死"。

## 4. 抓「用完就删」的中间文件

有些工具会把解密/中间产物写到 `%TEMP%` 再 `LoadLibrary`，用完即删。
用高频轮询临时目录（0.5 ms 级 `glob` + 立即复制）足够抢到（实测 763 KB 的 PE 能稳定抓到）。
比重写它的解密逻辑省事，但产物不可复现，只适合取证。

## 5. 环境噪声

`mamba run -n <env> python ...` 在本机会固定打印 5 行
`libmamba Error opening for writing ...mamba.bat: Permission denied`。
这是 shell 初始化脚本不可写导致的，**不影响解释器执行**；批量脚本里用
`2>&1 | grep -v libmamba` 过滤即可，不要去改 conda 安装目录权限。

## 6. 生成含反斜杠 / 二进制转义的文件

多层转义（bash heredoc → Python 字符串 → 目标语言）会把 `\\`、`\x00` 提前解释，
典型后果：Markdown 里的行连接符被吃掉、`.py` 源码里混入真正的 NUL 字节
（编辑器显示 "Binary file matches"，解释器报语法错误）。

规则：这类内容**用编辑工具直接写**，不要用 heredoc 拼接；写完自查
`python -c "print(open(p,'rb').read().count(b'\x00'))"`。
