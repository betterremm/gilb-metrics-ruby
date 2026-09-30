#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Графический интерфейс анализатора метрик Джилба для кода на Ruby.

Парсер написан на Python; GUI использует стандартную библиотеку tkinter
(дополнительных зависимостей не требуется).

Запуск:
    python3 gilb_gui.py
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import gilb_core


SAMPLE_CODE = '''# Пример: все циклы + ветвления + case/when + тернарный оператор.
def analyze_numbers(numbers)
  stats = { positive: 0, negative: 0, zero: 0 }

  numbers.each do |value|
    if value > 0
      stats[:positive] += 1
    elsif value < 0
      stats[:negative] += 1
    else
      stats[:zero] += 1
    end
  end

  total = 0
  for num in numbers
    total += num
  end

  index = numbers.length
  while index > 0
    index -= 1
  end

  attempts = 0
  until attempts >= 3
    attempts += 1
  end

  marks = 0
  3.times do |i|
    marks += i
  end

  { stats: stats, total: total, marks: marks }
end

def classify(avg)
  grade = case
          when avg >= 90
            "A"
          when avg >= 75
            "B"
          when avg >= 60
            "C"
          else
            "F"
          end
  grade
end

data = [5, -3, 0, 8, -1, 4]
result = analyze_numbers(data)
average = result[:total].to_f / data.length
label = average >= 0 ? "неотрицательное" : "отрицательное"
puts "Среднее: #{average} (#{label}), оценка: #{classify(average)}"
'''


class GilbApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Метрики Джилба — анализатор потока управления кода Ruby")
        self.geometry("1150x740")
        self.minsize(900, 600)

        self._build_toolbar()
        self._build_body()

    # -------------------- построение интерфейса --------------------

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(10, 8))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(bar, text="Открыть .rb файл…", command=self.on_open).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="Анализировать", command=self.on_analyze).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Загрузить пример", command=self.on_sample).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Очистить", command=self.on_clear).pack(side=tk.LEFT, padx=6)

        self.file_label = ttk.Label(bar, text="Файл не выбран", foreground="#5B6472")
        self.file_label.pack(side=tk.LEFT, padx=(12, 0))

    def _build_body(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # --- левая панель: исходный код ---
        left = ttk.Frame(paned)
        ttk.Label(left, text="Исходный код Ruby").pack(anchor=tk.W, pady=(0, 4))
        src_wrap = ttk.Frame(left)
        src_wrap.pack(fill=tk.BOTH, expand=True)

        self.source = tk.Text(src_wrap, wrap=tk.NONE, undo=True,
                              font=("Menlo", 12) if os.name != "nt" else ("Consolas", 11))
        yscroll = ttk.Scrollbar(src_wrap, orient=tk.VERTICAL, command=self.source.yview)
        xscroll = ttk.Scrollbar(left, orient=tk.HORIZONTAL, command=self.source.xview)
        self.source.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.source.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        src_wrap.rowconfigure(0, weight=1)
        src_wrap.columnconfigure(0, weight=1)
        xscroll.pack(fill=tk.X)
        paned.add(left, weight=2)

        # --- правая панель: результаты ---
        right = ttk.Frame(paned)
        ttk.Label(right, text="Результат — метрики Джилба",
                  font=("TkDefaultFont", 11, "bold")).pack(anchor=tk.W, pady=(0, 8))

        cards = ttk.Frame(right)
        cards.pack(fill=tk.X)
        self.cl_var = tk.StringVar(value="0")
        self.cl_rel_var = tk.StringVar(value="0.000")
        self.cli_var = tk.StringVar(value="0")
        self.formula_var = tk.StringVar(value="cl = CL / N = —")

        self._metric_card(cards, 0, "Абсолютная\nсложность CL", self.cl_var)
        self._metric_card(cards, 1, "Относительная\nсложность cl", self.cl_rel_var)
        self._metric_card(cards, 2, "Макс. уровень\nвложенности CLI", self.cli_var)
        for c in range(3):
            cards.columnconfigure(c, weight=1)

        ttk.Label(right, textvariable=self.formula_var, foreground="#5B6472").pack(anchor=tk.W, pady=(8, 10))

        ttk.Label(right, text="Детализация управляющих конструкций",
                  font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W, pady=(0, 4))

        cols = ("construct", "count", "cl", "note")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", height=12)
        self.tree.heading("construct", text="Конструкция")
        self.tree.heading("count", text="Кол-во")
        self.tree.heading("cl", text="Вклад в CL")
        self.tree.heading("note", text="Примечание")
        self.tree.column("construct", width=250, anchor=tk.W)
        self.tree.column("count", width=70, anchor=tk.CENTER)
        self.tree.column("cl", width=90, anchor=tk.CENTER)
        self.tree.column("note", width=280, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)

        paned.add(right, weight=3)

    def _metric_card(self, parent, col, title, var):
        card = ttk.Frame(parent, relief=tk.RIDGE, borderwidth=1, padding=10)
        card.grid(row=0, column=col, sticky="nsew", padx=4)
        ttk.Label(card, text=title, foreground="#5B6472", justify=tk.CENTER).pack()
        ttk.Label(card, textvariable=var, font=("TkDefaultFont", 26, "bold")).pack(pady=(4, 0))

    # -------------------- обработчики --------------------

    def on_open(self):
        path = filedialog.askopenfilename(
            title="Выберите файл Ruby",
            filetypes=[("Ruby", "*.rb"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                code = f.read()
        except OSError as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{e}")
            return
        self.source.delete("1.0", tk.END)
        self.source.insert("1.0", code)
        self.file_label.config(text="Файл: " + os.path.basename(path))
        self.analyze()

    def on_analyze(self):
        self.analyze()

    def on_sample(self):
        self.source.delete("1.0", tk.END)
        self.source.insert("1.0", SAMPLE_CODE)
        self.file_label.config(text="Загружен встроенный пример")
        self.analyze()

    def on_clear(self):
        self.source.delete("1.0", tk.END)
        self.file_label.config(text="Файл не выбран")
        self.cl_var.set("0")
        self.cl_rel_var.set("0.000")
        self.cli_var.set("0")
        self.formula_var.set("cl = CL / N = —")
        for item in self.tree.get_children():
            self.tree.delete(item)

    def analyze(self):
        code = self.source.get("1.0", tk.END)
        r = gilb_core.analyze(code)

        self.cl_var.set(str(r.cl))
        self.cl_rel_var.set(f"{r.cl_relative:.3f}")
        self.cli_var.set(str(r.cli))
        self.formula_var.set(f"cl = CL / N = {r.cl} / {r.n} = {r.cl_relative:.3f}")

        for item in self.tree.get_children():
            self.tree.delete(item)
        for b in r.breakdown:
            self.tree.insert("", tk.END, values=(b.construct, b.count, b.contribution_to_cl, b.note))


if __name__ == "__main__":
    GilbApp().mainloop()
