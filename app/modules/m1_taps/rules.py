import csv,io
from app.config import COLUMNS
from app.errors import DomainError
from app.reasons import reject,UNPROVEN_CODES
HEADER=",".join(COLUMNS).encode("ascii")
BOM=b"\xef\xbb\xbf"
TEXT_FIELDS=("route","note")
# 领域字符：线路别名与备注常用字。用于给两种候选解码打分，分差不达保证金即视为证据不足
DOMAIN_CHARS=set("路常规换乘早班未知线缺金额失败刷卡同键冲突补票月末合并流水备注站点上下高峰夜间空调")
MARGIN=2
def decode(raw):
    "整包回退解码，仅用于兼容旧调用；新流程按字节分段判定"
    for encoding in ("utf-8-sig","gb18030"):
        try: return raw.decode(encoding),encoding
        except UnicodeDecodeError: continue
    raise DomainError("ENCODING","无法识别文件编码")
def _score(text):
    "领域可信度评分：领域字+3，其余CJK+1，拉丁补充/控制区/私用区扣分"
    score=0
    for ch in text:
        o=ord(ch)
        if ch in DOMAIN_CHARS: score+=3
        elif 0x4E00<=o<=0x9FFF: score+=1
        elif ch in "\r\n\t" or 0x20<=o<0x7F: score+=0
        elif 0x7F<=o<=0xFF: score-=2
        elif 0xE000<=o<=0xF8FF or o==0xFFFD: score-=5
    return score
def _candidates(blob):
    "严格解码候选；候选必须让分段以表头开头（BOM可证伪GB18030解读）"
    found=[]
    if blob.startswith(BOM):
        try: found.append(("utf-8-sig",blob.decode("utf-8-sig")))
        except UnicodeDecodeError: pass
    else:
        try: found.append(("utf-8",blob.decode("utf-8")))
        except UnicodeDecodeError: pass
    try: found.append(("gb18030",blob.decode("gb18030")))
    except UnicodeDecodeError: pass
    head=",".join(COLUMNS)
    return [(enc,text) for enc,text in found if text.startswith(head)]
def _decide(blob):
    "裁决一段字节的编码。返回 (encoding, text, basis)；无法证明时 encoding 为 None，basis 为 (reason, detail)"
    cands=_candidates(blob)
    if not cands:
        for enc in ("utf-8-sig","gb18030"):
            try:
                blob.decode(enc)
                return None,None,("BAD_HEADER","分段表头不匹配")
            except UnicodeDecodeError: continue
        return None,None,("UNDECODABLE","字节区间在UTF-8与GB18030下均无法解码")
    if len(cands)==1:
        enc,text=cands[0]
        return enc,text,{"utf-8-sig":"bom","utf-8":"strict-utf8","gb18030":"strict-gb18030"}[enc]
    (e1,t1),(e2,t2)=cands
    if t1==t2: return e1,t1,"ascii-identical"
    s1,s2=_score(t1),_score(t2)
    if abs(s1-s2)<MARGIN: return None,None,("AMBIGUOUS_DECODING",f"两种解码均可行且证据不足:{e1}={s1}分,{e2}={s2}分")
    if s1>s2: return e1,t1,f"scored:{e1}={s1},{e2}={s2}"
    return e2,t2,f"scored:{e2}={s2},{e1}={s1}"
def _split_segments(raw):
    "按行首表头（可带BOM）把合并包切成字节段；每段对应一台车载机的流水"
    marks=[];pos=0;n=len(raw)
    while pos<n:
        p=pos+3 if raw[pos:pos+3]==BOM else pos
        if raw[p:p+len(HEADER)]==HEADER: marks.append(pos)
        nl=raw.find(b"\n",pos)
        if nl<0: break
        pos=nl+1
    if not marks: return [(0,n)]
    bounds=[]
    if marks[0]>0: bounds.append((0,marks[0]))
    for i,s in enumerate(marks): bounds.append((s,marks[i+1] if i+1<len(marks) else n))
    return bounds
def _text_lines(text):
    "按 \\n 切文本行并保留行尾，与csv读取器消耗行的方式一致"
    parts=text.split("\n")
    lines=[p+"\n" for p in parts[:-1]]
    if parts[-1]: lines.append(parts[-1])
    return lines
def _quarantine_lines(raw,s,e,seg_index,reason,detail,bad,excluded):
    "无法采用的段：按物理行逐条隔离或计空行，返回 (input增量, blank增量)"
    count=blank=0;pos=s;line=raw[:s].count(b"\n")
    while pos<e:
        nl=raw.find(b"\n",pos,e)
        end=e if nl<0 else nl+1
        piece=raw[pos:end];line+=1;count+=1
        if not piece.strip():
            blank+=1;excluded.append({"kind":"blank","_bytes":[pos,end]})
        else:
            bad.append({"_line":line,"_sources":[line],"_bytes":[pos,end],"_segment":seg_index,"_encoding":None,"_basis":detail,"_raw_hex":piece[:256].hex(),"reason":reason,"detail":detail})
        pos=end
    return count,blank
def evaluate(raw,context=None):
    if not raw: raise DomainError("EMPTY_FILE","文件为空")
    if not raw.strip(): raise DomainError("BLANK_ONLY","全部为空行")
    rows=[];bad=[];excluded=[];seen={};duplicate=blank=repeated=count=0;segments=[]
    for seg_index,(s,e) in enumerate(_split_segments(raw)):
        blob=raw[s:e]
        encoding,text,basis=_decide(blob)
        if encoding is None:
            reason,detail=basis
            if seg_index==0:
                if reason=="UNDECODABLE": raise DomainError("ENCODING","无法识别文件编码")
                if reason=="BAD_HEADER": raise DomainError("BAD_HEADER","表头不匹配")
            c,b=_quarantine_lines(raw,s,e,seg_index,reason,detail,bad,excluded)
            count+=c;blank+=b
            segments.append({"index":seg_index,"status":"unproven","reason":reason,"bytes":[s,e]})
            continue
        stream=csv.reader(io.StringIO(text,newline=""))
        try:
            header=next(stream,None)
            if header!=COLUMNS:
                if seg_index==0: raise DomainError("BAD_HEADER","表头不匹配")
                c,b=_quarantine_lines(raw,s,e,seg_index,"BAD_HEADER","分段表头不匹配",bad,excluded)
                count+=c;blank+=b
                segments.append({"index":seg_index,"status":"unproven","reason":"BAD_HEADER","bytes":[s,e]})
                continue
            bom_len=3 if encoding=="utf-8-sig" else 0
            codec="utf-8" if encoding=="utf-8-sig" else encoding
            offsets=[s+bom_len]
            for ln in _text_lines(text): offsets.append(offsets[-1]+len(ln.encode(codec)))
            if seg_index==0 and not count:
                excluded.append({"kind":"header","_bytes":[s,offsets[1]]})
            else:
                repeated+=1;count+=1;excluded.append({"kind":"repeated_header","_bytes":[s,offsets[1]]})
            line_offset=raw[:s].count(b"\n");prev=stream.line_num;accepted_before=len(rows)
            for cells in stream:
                count+=1;cur=stream.line_num
                line=line_offset+cur;span=[offsets[prev],offsets[cur]];prev=cur
                if not cells or not any(c.strip() for c in cells): blank+=1;excluded.append({"kind":"blank","_bytes":span});continue
                if cells==header: repeated+=1;excluded.append({"kind":"repeated_header","_bytes":span});continue
                row={"_line":line,"_sources":[line],"_raw":cells,"_bytes":span,"_encoding":encoding,"_basis":basis,"_segment":seg_index}
                if len(cells)!=len(header): bad.append(reject(row,"BAD_COLUMNS","列数不匹配"));continue
                row.update(dict(zip(header,[x.strip() for x in cells])))
                if not row[header[0]]: bad.append(reject(row,"EMPTY_VALUE","业务键为空"));continue
                key=row[header[0]]
                if key in seen:
                    previous=seen[key]
                    if cells==previous["_raw"]: duplicate+=1;excluded.append({"kind":"duplicate","_bytes":span})
                    else: bad.append(reject(row,"DUPLICATE_CONFLICT","同键不同值"))
                    continue
                seen[key]=row;rows.append(row)
        except csv.Error: raise DomainError("BAD_CSV","引号未闭合或文件损坏")
        segments.append({"index":seg_index,"status":"proven","encoding":encoding,"basis":basis,"bytes":[s,e],"rows":len(rows)-accepted_before})
    # 整包解释唯一性：同一字节串（线路/备注字段）在全包只得一种解码，否则其全部出现均未证明
    field_seen={}
    for row in rows:
        for field in TEXT_FIELDS:
            value=row.get(field)
            if not value: continue
            fb=value.encode("utf-8" if row["_encoding"]=="utf-8-sig" else row["_encoding"])
            if all(b<128 for b in fb): continue
            field_seen.setdefault((field,fb),{}).setdefault(value,[]).append(row)
    conflicted={}
    for (field,fb),readings in field_seen.items():
        if len(readings)<2: continue
        values=sorted(readings)
        for value,holders in readings.items():
            other=next(v for v in values if v!=value)
            for row in holders: conflicted.setdefault(id(row),(row,f"字段{field}的同一字节串在包内被解码为'{value}'与'{other}'"))
    if conflicted:
        kept=[]
        for row in rows:
            if id(row) in conflicted: bad.append(reject(row,"INTERPRETATION_CONFLICT",conflicted[id(row)][1]))
            else: kept.append(row)
        rows=kept
    if count==0: raise DomainError("HEADER_ONLY","仅有表头")
    if not rows and not bad: raise DomainError("BLANK_ONLY","全部为空行")
    families=sorted({"utf-8" if s["encoding"].startswith("utf-8") else s["encoding"] for s in segments if s.get("encoding")})
    if len(families)==1: encoding=families[0]+("-sig" if families[0]=="utf-8" and raw.startswith(BOM) else "")
    else: encoding="mixed"
    metrics={"input":count,"accepted":len(rows),"quarantine":len(bad),"duplicate":duplicate,"blank":blank,"repeated_headers":repeated,
             "encoding":encoding,"bytes":len(raw),"segments":len(segments),
             "unproven":sum(1 for r in bad if r["reason"] in UNPROVEN_CODES)}
    return {"rows":rows,"quarantine":bad,"excluded":excluded,"segments":segments,"metrics":metrics}
