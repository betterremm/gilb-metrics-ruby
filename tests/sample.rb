# sample.rb — подготовленная программа на Ruby для анализа метрик Джилба.
# Содержит ВСЕ операторы цикла языка (while, until, for, loop, итераторы
# each/times), операторы ветвления (if/elsif/else, unless) и оператор
# множественного выбора (case/when).

def analyze_numbers(numbers)
  stats = { positive: 0, negative: 0, zero: 0 }

  # Цикл-итератор each
  numbers.each do |value|
    # Ветвление if / elsif / else
    if value > 0
      stats[:positive] += 1
    elsif value < 0
      stats[:negative] += 1
    else
      stats[:zero] += 1
    end
  end

  # Цикл for
  total = 0
  for num in numbers
    total += num
  end

  # Цикл while
  index = numbers.length
  doubled = []
  while index > 0
    index -= 1
    doubled << numbers[index] * 2
  end

  # Цикл until
  attempts = 0
  until attempts >= 3
    attempts += 1
  end

  # Цикл-итератор times
  marks = 0
  3.times do |i|
    marks += i
  end

  { stats: stats, total: total, doubled: doubled, marks: marks }
end

# Оператор множественного выбора case (классификация по среднему значению).
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

# Бесконечный цикл loop с условием выхода (unless — ветвление).
def find_threshold(values, limit)
  i = 0
  loop do
    break unless i < values.length
    break if values[i] > limit
    i += 1
  end
  i
end

data = [5, -3, 0, 8, -1, 4]
result = analyze_numbers(data)
average = result[:total].to_f / data.length

# Тернарный оператор ?:
label = average >= 0 ? "неотрицательное" : "отрицательное"

puts "Среднее: #{average} (#{label}), оценка: #{classify(average)}"
puts "Порог достигнут на позиции #{find_threshold(data, 7)}"
