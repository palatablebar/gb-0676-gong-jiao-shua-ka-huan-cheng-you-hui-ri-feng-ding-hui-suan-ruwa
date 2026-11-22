# 公交刷卡换乘优惠与日封顶回算

供公交清分中心复核员核对原始记录、处理差异并封存证据。

## 启动

```sh
docker compose up --build -d
docker compose exec -T app pytest -q
```

打开 http://localhost:18245 。首次进入自动运行仓内脏样例。工具条可重跑、切换样例或上传CSV。SQLite保存在命名卷records中，重建服务保留批次。

## 模块

- 1. 刷卡采信：`/taps`，`/api/taps`。
- 2. 线路换乘：`/routes`，`/api/routes`。
- 3. 票价版本：`/fares`，`/api/fares`。
- 4. 行程配对：`/journeys`，`/api/journeys`。
- 5. 优惠回算：`/discounts`，`/api/discounts`。
- 6. 清分对账：`/clearing`，`/api/clearing`。
- 7. 日结归档：`/settlement`，`/api/settlement`。
- 复核证据：`/review`，沿来源字节区间查看解码值、线路归属、换乘和封顶结果，查验卡日应收与封存状态。

## 核心规则

换乘按上次有效付费行程的时间窗计算，优惠与日封顶按确定顺序裁决并保留分币守恒。月末合并包混合UTF-8与GB18030流水时，按分段表头切字节段逐段判定编码并逐条标注依据，同一字节串全包只许一种解释；任一行无法证明解释前不得封存，裁决全文见 `docs/ADJUDICATION.md`。

## 演示

1. 打开首页，核对当次计算、差异和隔离原因。
2. 切换模块查看源行及裁决依据；打开 `/review` 沿字节区间查验解码值与卡日应收。
3. 重跑相同样例，批次号与行数保持一致（响应`reused`为真，不新增采信记录）。
4. 切换样例到"月末合并·混合编码批"，查看同一卡号跨编码合并出的唯一卡日应收。
5. 复核后导出一份证据CSV。版本已变化的复核提交返回409且旧版完整保留；存在未证明解释行时已复核与导出均返回409。

## 输入与输出

输入列见 `docs/DATA-DICTIONARY.md`。项目包含dirty.csv、clean.csv、legacy.csv、mixed.csv，统一走实际导入路径。上传限制4MB，拒绝不带时区的时间。业务键按字符串保留，Decimal参与计算，空值不会当零。

`POST /api/runs` 接收sample或csv；`GET /api/runs`返回历史批次；`POST /api/runs/<id>/review`需要version与decision；`GET /api/runs/<id>/bytes`按字节区间回读原始包；`GET /api/runs/<id>/archive`返回唯一证据导出。原始字节按摘要入库只增不删。

## 范围

样例均为虚构。单机复核工具不连接生产系统；不提供登录、远端数据库或自动支付。内存计算按4MB输入上限控制，SQLite事务保证结果完整写入。

## 目录

app为服务与规则，sample_data为输入，tests为测试，docs为定义与深度登记。
