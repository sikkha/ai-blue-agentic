# Status update

บันทึกความคืบหน้ารายสัปดาห์ รายการใหม่อยู่บนสุด

---

## 18 พ.ย. 2569 (18 November 2026) — เปิดใช้งาน AI-Blue พร้อมบัญชี native บน GCP

- **รุ่นที่ให้บริการ:** [AI-Blue](https://public.geopolitics.io/) ใช้ commit `60ead4f51f932f8c4cdc5438fa92071f0f6f2070` ที่ `/opt/ai-blue/native-current` โดย Nginx ส่งคำขอไปยัง `ai-blue-native.service` บน `127.0.0.1:8186` บัญชีใช้ Argon2id และ session ฝั่งเซิร์ฟเวอร์พร้อม CSRF แยก workspace และสิทธิ์ agent ตามบัญชี การแก้บัญชีต้องมี session ผู้ดูแลที่ยังใช้ได้ และจำกัดความถี่ลงชื่อเข้าใช้ตามคู่ชื่อผู้ใช้กับ IP
- **GCP และ Cloudflare:** ผู้ดูแลรายงานว่า TCP 443 เปิดรับเฉพาะช่วง IPv4 ของ Cloudflare และการเชื่อมตรงจาก Mac หมดเวลา Cloudflare Rule simulator แสดงว่า Strict ตรงกับ hostname นี้ คำขอทดสอบใหม่ผ่าน Cloudflare บันทึกที่ origin ว่าใช้ `443`, `https`, `TLSv1.3` หน้าแนะนำเดิมตอบ 200 และ workspace API ตอบ 404 ก่อนเปลี่ยนเส้นทาง ตัวจับเวลาต่ออายุใบรับรองยังทำงาน
- **ตรวจอัตโนมัติ:** ตรวจไฟล์ใน release ทั้ง 221 รายการกับ commit และตรวจ Nginx ผ่าน ตัวตรวจภายนอกเห็นหน้า React และได้ 401 จาก API workspace และบัญชีผู้ดูแลเมื่อยังไม่ลงชื่อเข้าใช้ `internal.geopolitics.io` ยังเปลี่ยนเส้นทางไปลงชื่อเข้าใช้ (302) และ `research.geopolitics.io` ตอบ 200 รุ่นที่ให้บริการผ่าน CI และชุดทดสอบ Python 279 รายการกับ 6 subtests
- **ตรวจผ่านเบราว์เซอร์:** ผู้ดูแลยืนยันว่า `kan` ลงชื่อเข้าใช้ผ่าน hostname สาธารณะได้ เปิด workspace แล้วเห็นโน้ตสองรายการและกราฟ
- **ตรวจ agent ใน production:** บัญชี `kan` เปิดสิทธิ์ agent และโปรเซสที่ให้บริการได้รับค่า `GROQ_API_KEY` แล้ว trace มีหนึ่ง session สถานะ `done` และสี่ขั้นจากโมเดลที่รายงานการใช้รวม 5,661 tokens จึงยืนยันการเรียกโมเดลจริงสำหรับ turn นี้ การทดสอบ upload และการอนุมัติเครื่องมือกับโมเดลจริงผ่านเบราว์เซอร์ยังไม่มีหลักฐานยืนยัน
- **ย้อนกลับ:** ใช้ `/var/backups/ai-blue/native-auth-rollbacks/overview-tls-cloudflare.conf` ซึ่งเก็บ origin TLS, ขอบเขตการเข้าถึงของ Cloudflare และเส้นทางต่ออายุใบรับรอง ขั้นตอนอยู่ใน [คู่มือการติดตั้ง](../deploy/native-auth.md)

---

## 18 พ.ย. 2569 — เผยแพร่หน้าแนะนำ AI-Blue บน GCP

หน้า [AI-Blue](https://public.geopolitics.io/) เผยแพร่จาก commit `77eb6783f02199fbedebbee39ff46b89221e264e`
เป็นหน้า HTML แบบอ่านอย่างเดียวที่ Nginx ให้บริการ ส่วน React UI และ FastAPI ทำงานใน `ai-blue.service`
ที่ `127.0.0.1:8180` สำหรับผู้มีสิทธิ์ SSH หน้าเว็บสาธารณะไม่มีเส้นทางไปยัง API, แชต หรือ workspace

ตรวจแล้วว่า HTTPS ของหน้าสาธารณะตอบ 200 และเส้นทาง API ที่ทดสอบตอบ 404 ส่วน `internal.geopolitics.io`
ยังใช้ Cloudflare Access และ `research.geopolitics.io` ตอบ 200 การทดสอบ Python ผ่าน 268 รายการ
และ 6 subtests รวมทั้ง Ruff, ESLint และ frontend build

โค้ดหน้าเว็บใน checkout เพิ่มบัญชี native, ผู้ดูแลระบบ, session/CSRF และ workspace แยกตามบัญชีแล้ว
ยังใช้หน้าแนะนำใน production ระหว่างรอใบรับรอง origin, การอนุญาต ingress 443 และ Full (strict) เฉพาะ hostname
ขั้นตอนสร้างผู้ดูแลและ rollback อยู่ใน [`deploy/native-auth.md`](../deploy/native-auth.md)

---

## สัปดาห์ที่ 4 (13–14 ต.ค. 2569) — โครง AI-Blue, workspace ของโน้ต และ GraphRAG

**สถานะ:** เสร็จ · 268 offline tests · ruff, ESLint + @shadcn/lint, build · CI

1. **โครง AI-Blue ของวิชา** — ย้ายโค้ดเข้า `core/agentic_ai` (runtime, tools, models, tracing, retrieval, integrations),
   `backend/`, `frontend/`, `launcher/` พร้อม test ขอบเขต (แกนกลางไม่ import ชั้นนอก ไม่ใช้ framework ของ agent), prompt
   เป็นไฟล์ใน `prompts/`, event และรูปแบบ step ของ trace ใน `messages/`, pyproject + ruff
2. **workspace ของโน้ต** — โฟลเดอร์ markdown ที่ทุก session ใช้ร่วมกัน เครื่องมือใหม่ `list` `mkdir` `move` `append` `delete`
   (ลงถังขยะ) การแก้โน้ตต้องอนุมัติ ทุกการเปลี่ยนแปลงส่ง `file.changed` — `tools/builtin.py`, `runtime/loop.py`
3. **index ถาวร** — SQLite: หัวข้อ markdown + vector e5 + FTS5 ที่ตัดคำไทยแล้ว อัปเดตเฉพาะหัวข้อที่เปลี่ยน ย้ายไฟล์ไม่ต้อง
   embed ใหม่ ค้นทั้งหมดหรือรายโฟลเดอร์ — `retrieval/workspace_index.py`
4. **GraphRAG** — library ของวิชาบนแกนของเรา (`integrations/knowledge_graph/`) + graph ของ workspace: `[[link]]`,
   backlinks, triple ต่อหัวข้อ (อ่านเฉพาะหัวข้อใหม่ หลายหัวข้อต่อคำขอ หยุดที่งบ) และความสัมพันธ์ต่อท้ายผลของ `rag_search`
5. **web UI** — สามส่วนแบบ Obsidian: ต้นไม้ไฟล์, ตัวแก้ CodeMirror (live preview) / graph (sigma.js), แชตพร้อมเลือกโฟลเดอร์ที่ค้น,
   diff บนการ์ดอนุมัติ, แหล่งอ้างอิงเป็นปุ่มเปิดโน้ต, บรรทัดสถานะ, สิ่งที่เปิดอยู่เก็บใน URL (reload กลับมาที่เดิม)

ผลจริง (workspace ตัวอย่าง 5 โน้ต): สร้าง graph 11 หัวข้อในคำขอเดียว 2,387 tokens 3 วินาที; ค้นรายโฟลเดอร์ 80 ms;
คำถามที่ต้องเชื่อมสองโน้ต PASS ใน 4 actions 9,952 tokens พร้อมอ้างหัวข้อ; เขียนโน้ตใหม่ผ่านการอนุมัติ PASS
และโน้ตขึ้นใน backlinks ทันที; โมเดลบางครั้งตอบด้วยรูปแบบ tool call ของตัวเองแทน JSON ซึ่ง engine อ่านรูปแบบนั้นได้ด้วย

---

## สัปดาห์ที่ 3 (30 ก.ย. – 5 ต.ค. 2569) — RAG: benchmark 5 แบบ และไฟล์ที่แนบใน agent

**สถานะ:** เสร็จ · 153 offline tests · CI

1. **benchmark RAG 5 แบบ** (hybrid, graph, agentic, corrective, multimodal) ตาม notebook ของวิชา บน PDF จริง
   อังกฤษ 149 หน้า + ไทย 30 หน้า — วัดทั้งต้นทุน/ความเร็ว (แบบของวิชา) และ**คุณภาพ** (67 คำถามพร้อมหน้าที่ถูก)
   รวมถึงแบบที่ให้ LLM วางแผนหรือคัดช่วง, ตอบจริงทั้งระบบ และความแม่นของ OCR — `bench/rag/`
2. **ไฟล์ที่แนบใน agent** — `run --file`, `/attach` ใน chat ไฟล์สั้นใส่ทั้งไฟล์ ไฟล์ยาวทำ index ชั่วคราวใน session
   แล้วค้นด้วย tool `rag_search` (เครื่องมือตัวที่ 9) ชนิดการค้นตั้งใน `workflow.yaml` — `rag.py`, `tools.py`
3. **OCR** ผ่านโมเดล vision บน Groq (role `ocr`) เฉพาะหน้าที่ไม่มีข้อความ ปิดเป็นค่าตั้งต้น ช่วงที่มาจาก OCR มีป้ายเตือน
4. **ภาษาไทย** — ตัดคำด้วย PyThaiNLP สำหรับ BM25, เลขไทยแปลงเฉพาะในรูปที่ใช้จับคู่
5. **Web UI** (`main.py serve`) — แชต, ประวัติ session, การ์ด tool, อนุมัติในแชต, ปุ่ม Stop, แนบไฟล์, meter, settings
   ที่เขียนกลับลง yaml และ trace; engine ย่อ output เก่าให้คำขอไม่เกินเพดานต่อครั้งของ plan และ review เฉพาะ turn ที่ใช้ tool

ผลจริง: hybrid ดีที่สุดในแบบที่ไม่ใช้โมเดล (hit@5 0.878, MRR 0.779) และเป็นค่าตั้งต้น; graph/agentic/corrective
แบบกฎให้ผลเหมือนฐานของมันทุกข้อเพราะคะแนน e5 อยู่ที่ 0.85–0.92 ทุกคำถาม รวมถึงคำถามที่ไม่มีคำตอบ — คะแนนความคล้าย
บอก "ไม่มีในเอกสาร" ไม่ได้; ให้ LLM คัดช่วงช่วยคำถามที่ใช้คำต่าง (MRR 0.654 → 0.742) แต่ใช้ ~2,900 tokens ต่อคำถาม;
ภาษาไทยตัดคำแล้ว hybrid MRR 0.806 → 0.922; embedding บน GPU 1.4 วินาทีต่อ 319 ช่วง (CPU 24 วินาที), ค้นหนึ่งครั้ง ~15 ms;
agent ตอบจากรายงาน 72 หน้าด้วย `rag_search` 3 ครั้ง อ้างเลขหน้า PASS; คำตอบทั้งระบบ RAG ถูก 15/18 และปฏิเสธคำถามที่
ไม่มีคำตอบครบ 4/4; OCR ภาษาไทยอ่านข้อความได้แต่ตัวเลขถูกตรงตัวเพียง 43–50% — ต้องตรวจซ้ำก่อนใช้ตัวเลข

---

## สัปดาห์ที่ 2 (23–29 ก.ย. 2569) — tools, CLI, traceability

**สถานะ:** เสร็จ · 100 offline tests (ไม่ต้องมี key ไม่ต่อเน็ต) · CI

ครบโจทย์ 6 ข้อ แต่ละข้อชี้ไฟล์ได้

1. **เครื่องมือ** — 8 ตัว (`bash read write edit glob grep webfetch websearch`) ค้นเว็บผ่าน Firecrawl
   และสำรองด้วย Exa **ไม่ต้องมี key** `webfetch` คืน markdown เฉพาะเนื้อหาหลัก และใช้ Firecrawl เมื่อเว็บบล็อก
   หรือต้องรัน JavaScript
2. **ทะเบียนเครื่องมือเป็น JSON + permission** — `config/tools.json` เป็น source of truth ของสิ่งที่โมเดลเห็น
   argument ถูกตรวจก่อนเรียกทุกครั้ง permission แบบ allow / ask / deny (rule สุดท้ายที่ match ชนะ,
   คำสั่ง shell ถูกตัดสินทีละคำสั่ง) ปฏิเสธพร้อมเหตุผลที่ส่งกลับให้โมเดลได้
3. **CLI** — `run` / `chat` / `export` / `tools` / `trace` คำตอบไป stdout ความคืบหน้าไป stderr,
   `--format json`, exit code คุยโต้ตอบกับ agent ใน session เดียวได้ (`chat`, `run -c`)
   และทุก session มี `transcript.json`
4. **trace database** — `sandbox/trace.db` หนึ่งแถวต่อข้อความของผู้ใช้ ต่อ action (พร้อมผลตัดสินของ permission
   และโมเดลที่ตอบ) และต่อคำตัดสินของ reviewer ตอบได้ว่า agent ขออะไรแล้ว*ถูกปฏิเสธ* ไม่ใช่แค่ทำอะไร
5. **yaml ยังเป็น config** — `workflow.yaml` + `runtime.yaml` ในรูปแบบ router ของวิชา (role → model → vendor)
6. **`dev_mem/`** — สองไฟล์นี้

ผลจริง: งานปกติ 9 แบบผ่านทั้งหมดใน 1–5 actions (1,703–13,259 tokens) รวมงานที่ต้องใช้ `edit`, ค้นเว็บ
และดึงหน้าที่ Cloudflare บล็อก บทสนทนา 4 turn ใน session เดียวผ่านทุก turn การทดลองขอบเขต: rule `deny`
หยุด `rm` ได้แม้ต่อสายกับคำสั่งอื่นและใส่ `--yes`, เมื่อสั่งให้พิมพ์ environment agent ตอบว่าไม่มี
`GROQ_API_KEY` และสแกนไม่พบ key ใน trace, log หรือ git history

---

## สัปดาห์ที่ 1 (20 ก.ย. 2569) — mini agent

**สถานะ:** เสร็จ · [github.com/NithichoteC/mini-agent](https://github.com/NithichoteC/mini-agent)

ทำ agent ที่รับงานเป็นภาษาธรรมดา เลือก action เอง ทำงานในโฟลเดอร์ของตัวเอง แล้วมี reviewer ตัดสิน

- เครื่องมือ 5 ตัว (จัดการไฟล์, รัน Python, ดึงเว็บ) ทำงานในโฟลเดอร์ของ session เท่านั้น
- ตัวหยุด 3 แบบ: งบ action, การทำ action ซ้ำ, คำตัดสิน BLOCKED — ทุกกรณีส่งต่อให้คนช่วยแล้วทำต่อได้
- agent ใช้ `qwen/qwen3.8-27b`, reviewer ใช้ `openai/gpt-oss-120b` (Groq)
- 31 offline tests รันได้โดยไม่ต้องมี API key, CI รันทุก push

ผลจริง: งานปกติ 4 แบบผ่านทั้งหมด ใช้ 1–4 actions (702–3,046 tokens)
เมื่อถอดเครื่องมือเขียนไฟล์ออก agent รายงานว่าทำไม่ได้ใน 3 actions แทนที่จะวนจนหมดงบ
