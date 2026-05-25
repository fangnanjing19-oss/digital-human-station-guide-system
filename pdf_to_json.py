import os
import fitz  # PyMuPDF 的库名
import json
import re

# --- 配置路径 ---
PDF_FOLDER = "raw_pdfs"  # 你的 17 个 PDF 放这里
OUTPUT_JSON = "knowledge_base.json"  # 输出给 AI 吃的数据


def clean_text(text):
    """清洗文本，去除多余的空格、换行符和乱码"""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)  # 把多个空格/换行压缩为一个
    return text.strip()


def process_pdfs():
    all_chunks = []

    # 遍历文件夹里的所有 pdf
    for filename in os.listdir(PDF_FOLDER):
        if not filename.endswith(".pdf"):
            continue

        filepath = os.path.join(PDF_FOLDER, filename)
        print(f"📄 正在解析: {filename} ...")

        try:
            # 打开 PDF 文件
            doc = fitz.open(filepath)

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text("text")  # 提取纯文本

                # 按换行符进行初步的段落切片
                paragraphs = text.split('\n\n')

                for para in paragraphs:
                    cleaned_para = clean_text(para)

                    # 过滤掉太短的无意义字符（比如单独的页码）
                    if len(cleaned_para) > 20:
                        chunk_data = {
                            "source": filename,
                            "page": page_num + 1,  # 页码从 1 开始
                            "content": cleaned_para
                        }
                        all_chunks.append(chunk_data)

            doc.close()
        except Exception as e:
            print(f"❌ 解析 {filename} 时出错: {e}")

    # 将所有切片保存为 JSON 文件
    print(f"\n✅ 提取完成！共生成 {len(all_chunks)} 个知识切片。")
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=4)
    print(f"💾 数据已保存至: {OUTPUT_JSON}")


if __name__ == "__main__":
    if not os.path.exists(PDF_FOLDER):
        os.makedirs(PDF_FOLDER)
        print(f"已创建 {PDF_FOLDER} 文件夹，请把 PDF 放进去后重新运行！")
    else:
        process_pdfs()