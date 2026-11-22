REASONS={"BAD_COLUMNS":"列数不匹配","EMPTY_VALUE":"必填值为空","INVALID_NUMBER":"数字格式错误","INVALID_TIME":"时间缺少偏移或格式错误","DUPLICATE_CONFLICT":"同键取值冲突","UNKNOWN_REFERENCE":"引用不存在","STALE_VERSION":"版本已更新","EMPTY_FILE":"文件为空","HEADER_ONLY":"仅有表头","BLANK_ONLY":"全部为空行","UNDECODABLE":"字节区间在UTF-8与GB18030下均无法解码","AMBIGUOUS_DECODING":"两种解码均可行且证据不足","INTERPRETATION_CONFLICT":"同一字节串在包内出现两种解释","UNPROVEN_INTERPRETATION":"存在无法证明解释的来源行，不得封存","BAD_HEADER":"表头不匹配"}
# 无法证明解释的原因码：携带这些原因的来源行未获证明，批次不得封存
UNPROVEN_CODES={"UNDECODABLE","AMBIGUOUS_DECODING","INTERPRETATION_CONFLICT"}
def reject(row, code, detail):
    return {**row,"reason":code,"detail":detail}
def sources(row):
    return row.get("_sources", [row.get("_line",0)])
def unproven(rows):
    return [row for row in rows if row.get("reason") in UNPROVEN_CODES]
