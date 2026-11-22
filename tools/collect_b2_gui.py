"""本机图形窗口接收 B2 密钥，支持粘贴并以 DPAPI 加密保存。"""
import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from upload import protect_token

TARGET = Path(__file__).resolve().parent / "b2-credentials.dpapi"

def save_credentials(key_id, application_key, target=TARGET):
    key_id, application_key = key_id.strip(), application_key.strip()
    if not key_id or not application_key:
        raise ValueError("两项都需要粘贴；圆点和字数可以确认是否已输入。")
    if any(character.isspace() for character in key_id + application_key):
        raise ValueError("密钥中包含空格或换行，请分别复制 keyID 和 applicationKey。")
    encrypted = protect_token(json.dumps({"keyId": key_id, "applicationKey": application_key}))
    # 排他创建，避免覆盖已有凭据。
    with target.open("x", encoding="ascii") as output:
        output.write(encrypted)

def main():
    window = tk.Tk()
    window.title("Typora 图床 — 保存受限 B2 密钥")
    window.geometry("560x340")
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=22)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="密钥名称：cloudflare-imgbed-typora\n只允许访问 slanwyf-typora-imgbed；Read and Write", justify="left").pack(anchor="w")
    variables = [tk.StringVar(window), tk.StringVar(window)]
    entries = []
    for label, value in zip(["keyID", "applicationKey"], variables):
        ttk.Label(frame, text=label + "（点击输入框，按 Ctrl+V 粘贴）").pack(anchor="w", pady=(12, 2))
        entry = ttk.Entry(frame, textvariable=value, show="●", width=64)
        entry.pack(fill="x")
        entries.append(entry)
    status = tk.StringVar(window)
    def refresh(*_):
        status.set(f"已输入：keyID {len(variables[0].get().strip())} 字符；applicationKey {len(variables[1].get().strip())} 字符")
    for value in variables:
        value.trace_add("write", refresh)
    ttk.Label(frame, textvariable=status).pack(anchor="w", pady=(10, 4))
    refresh()
    def save():
        try:
            save_credentials(variables[0].get(), variables[1].get())
        except ValueError as error:
            messagebox.showerror("尚未保存", str(error), parent=window)
            return
        except FileExistsError:
            messagebox.showerror("尚未保存", "已存在加密密钥文件，请告诉我后再处理，避免覆盖。", parent=window)
            return
        except Exception as error:
            (TARGET.parent / "collect-b2-error.log").write_text(type(error).__name__, encoding="utf-8")
            messagebox.showerror("尚未保存", "本机保存失败：" + type(error).__name__ + "。错误类型已记录在 D 盘。", parent=window)
            return
        for value in variables:
            value.set("")
        messagebox.showinfo("保存完成", "密钥已加密保存在 D 盘。关闭窗口后告诉我，我会验证桶范围并继续部署。", parent=window)
        window.destroy()
    ttk.Button(frame, text="加密保存", command=save).pack(anchor="e", pady=(14, 0))
    entries[0].focus_set()
    window.mainloop()

if __name__ == "__main__":
    main()
