# example_case.rb — контрольный пример правил подсчёта.
# Оператор множественного выбора case с тремя ветвями when (и else).
# Ожидается: CL = 3 (три when, else не считается), CLI = 2 (0,1,2).

def classify(x)
  case
  when x < 0
    y = 0
  when x == 0
    y = 1
  when x < 10
    y = 2
  else
    y = 3
  end
  y
end
