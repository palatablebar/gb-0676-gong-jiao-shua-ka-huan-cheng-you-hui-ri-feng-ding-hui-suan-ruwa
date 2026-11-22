# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存，响应含reused标记：同包重试复用既有批次，不新增采信记录。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file，原始字节按摘要入blobs表只增不删。/api/runs/<id>/bytes?start&end按字节区间回读原始包，返回hex与utf-8/gb18030双候选解码，供复核页沿区间查验。/api/runs/<id>/archive导出唯一证据CSV，含字节区间、编码与判定依据列；存在无法证明解释的来源行时，archive与"已复核"提交均返回409（UNPROVEN_INTERPRETATION），版本过期返回409（STALE_VERSION）且旧版本完整保留。
