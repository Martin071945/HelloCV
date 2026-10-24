# HelloCV
这是HITWH联创算法纳新任务仓库

【更新】第三周任务：ROS2学习实践
相关学习文档资料如下：https://www.yuque.com/martin1945/gtet4n/ftreqmpo0wf25ptu?singleDoc# 《第三周任务——ROS2学习实践》
在此次任务中，我从零搭建了ROS2工作空间，学习了节点的编写，并实操了 Topic、Service、Parameter、TF、Action 以及 Launch 等核心通信机制，最终试着模拟了校内赛 perception -> action 综合链路的小 demo。
本次实操从基础到综合，完成了以下模块的编写与调试：
基础通信：
编写了最简节点 hello_node 验证环境。
实现了 talker 和 listener，掌握 rclcpp::Publisher/Subscription 和 QoS 队列深度。
实现了 add_two_ints 的服务端与客户端，理解 Request-Response 模型。
参数与坐标变换：
编写 param_node，声明参数并实现终端动态修改（免编译调参）。
编写 tf_broadcaster，发布 base_link -> laser 的静态坐标变换，并使用 view_frames 生成 TF 树。



第一周任务：Linux安装与学习、Git学习
主要通过实操Linux的安装，结合理论知识学习，熟悉Linux及相应工具的使用逻辑；另一方面，基本掌握Git的使用方法，更好地适应协同工作。
相关学习文档资料如下：
1. Linux安装与学习：https://www.yuque.com/martin1945/gtet4n/zowty27gsznygiyx?singleDoc# 《第一周任务——Linux安装与学习记录》
2. Git理论学习：https://www.yuque.com/martin1945/gtet4n/dknemhu07rmzbvqa?singleDoc# 《第一周任务——Git理论学习》
3. Git实操：https://www.yuque.com/martin1945/gtet4n/qy13e1s7ofpxcy7x?singleDoc# 《第一周任务——Git任务实践》

第二周任务：CMake与LLM学习
掌握CMake的基础指令，理解CMake编译的逻辑；体会大语言模型的强大实力，提升与AI对话能力，培养花费更少Token达成目标的能力。
相关学习文档资料如下：
1. CMake理论学习：https://www.yuque.com/martin1945/gtet4n/phlmsgw814sgvq9k?singleDoc# 《第二周任务——CMake理论学习》
2. CMake任务实践：https://www.yuque.com/martin1945/gtet4n/ghg8vofbnqie6p02?singleDoc# 《第二周任务——CMake任务实践》
3. LLM学习与应用：https://www.yuque.com/martin1945/gtet4n/cafg6s98y2zcba3t?singleDoc# 《第二周任务——LLM学习与应用》

【关于LLM的学习提要】
实际上，需要补全的的网关文件各自承担的任务如下：
`config.py`	存“这次运行的全部参数”
`prompts.py`	存“怎么跟模型说话”
`json_guard.py`	将文本翻译为 Python 能够理解的语句
`rules.py`	存决策（校验字段/归一/兜底等）
`client.py`	发送 HTTP、重试、只取答案
`app.py`	指定输入输出是“一行进一行出”
`game.py`	存对局规则，包括对手策略、裁判、记分

对于补全后的代码，根据`README.md`的要求进行验证能够跑通，需要如下指令：
(1)93个测试
```bash
cd ../skeleton
python3 selfcheck.py
```
运行后，出现“所有TODO”都实现完了，并提示93个测试全部完整，证明我们的网关代码补全正确。
(2)正常游戏
```bash
export DEEPSEEK_API_KEY=sk-xxx #xxx处为个人API key
python3 play_chat.py --rounds 10
```
运行后应当能够进入剪刀石头布的游戏界面，并进行各种操作。

