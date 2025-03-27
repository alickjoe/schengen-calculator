# 文件名: schengen_calculator.py
from flask import Flask, request, render_template_string
from datetime import datetime, timedelta
import re
import json
import redis
r = redis.Redis(
    host='redis-19453.c295.ap-southeast-1-1.ec2.redns.redis-cloud.com',
    port=19453,
    decode_responses=True,
    username="az",
    password="9-!fMa57TRs-TTA"
)

app = Flask(__name__)

LANGUAGES = {
    "en": {
        "title": "Schengen Stay Calculator",
        "instructions": "Enter travel dates (MM/DD/YYYY format) with entry and exit separated by space/tab:",
        "example": """Example:
03/21/2025 04/23/2025
01/10/2025 01/31/2025
10/19/2024 11/18/2024""",
        "next_entry": "Next Entry Date (MM/DD/YYYY)*",
        "calculate": "Calculate",
        "error_date_format": "Invalid date format (MM/DD/YYYY)",
        "error_date_order": "Exit date cannot be earlier than entry date",
        "result_previous": "Days stayed in last 180 days before final exit: {}",
        "result_next": "Maximum allowed stay after next entry: {} days",
        "overstay_warning": "⚠️ No available days left (90/180 rule limit reached)",
        "final_exit_date": "Final exit date: {}",
        "save_name": "Save as name",
        "load_name": "Load record name",
        "save_button": "Save",
        "load_button": "Load",
        "error_load": "Record not found"
    },
    "zh": {
        "title": "申根停留天数计算器",
        "instructions": "输入旅行日期（MM/DD/YYYY格式），出入境日期用空格/tab分隔：",
        "example": """示例：
03/21/2025 04/23/2025
01/10/2025 01/31/2025
10/19/2024 11/18/2024""",
        "next_entry": "下次入境日期 (MM/DD/YYYY)*",
        "calculate": "计算",
        "error_date_format": "日期格式错误 (MM/DD/YYYY)",
        "error_date_order": "离开日期不能早于进入日期",
        "result_previous": "最后离境前180天内已停留天数：{} 天",
        "result_next": "下次入境后最多可停留天数：{} 天",
        "overstay_warning": "⚠️ 无可用天数（已达90/180规则限制）",
        "final_exit_date": "最后离境日期：{}",
        "save_name": "保存为名称",
        "load_name": "加载记录名称",
        "save_button": "保存",
        "load_button": "加载",
        "error_load": "记录未找到"
    }
}

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{{ texts.title }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .container { max-width: 800px; margin: 20px auto; }
        .language-switch { position: absolute; top: 10px; right: 10px; }
        .text-input { 
            width: 100%; 
            height: 200px; 
            font-family: monospace;
            white-space: pre;
            padding: 10px;
        }
        .error { color: red; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <div class="language-switch">
            <button onclick="switchLanguage('en')">EN</button>
            <button onclick="switchLanguage('zh')">中文</button>
        </div>
        
        <h2 class="my-4">{{ texts.title }}</h2>
        <p>{{ texts.instructions }}</p>
        
        <form method="POST" id="mainForm">
            <div class="mb-3">
                <textarea 
                    class="form-control text-input" 
                    name="travel_dates" 
                    placeholder="{{ texts.example }}"
                >{{ travel_dates }}</textarea>
            </div>
            
            <div class="mt-4">
                <label>{{ texts.next_entry }}</label>
                <input 
                    type="text" 
                    name="next_entry" 
                    class="form-control" 
                    value="{{ next_entry }}"
                    placeholder="MM/DD/YYYY"
                    required
                >
            </div>
            
            {% if error %}
            <div class="alert alert-danger mt-3">{{ error }}</div>
            {% endif %}
            
            {% if result is not none %}
            <div class="alert alert-success mt-3">
                <p>{{ texts.final_exit_date.format(last_exit_date) }}</p>
                <p>{{ texts.result_previous.format(previous_days) }}</p>
                {% if result > 0 %}
                    <p>{{ texts.result_next.format(result) }}</p>
                {% else %}
                    <p>{{ texts.overstay_warning }}</p>
                {% endif %}
                <p class="mt-2"><small>Based on Schengen 90/180-day rule</small></p>
            </div>
            {% endif %}

            {% if load_error %}
            <div class="alert alert-danger mt-3">{{ load_error }}</div>
            {% endif %}
            
            <button type="submit" class="btn btn-primary mt-3">{{ texts.calculate }}</button>
            <div class="mt-3">
                <label>{{ texts.save_name }}</label>
                <input 
                    type="text" 
                    name="save_name" 
                    class="form-control" 
                    value="{{ save_name }}"
                >
                <button type="submit" name="action" value="save" class="btn btn-secondary mt-2">
                    {{ texts.save_button }}
                </button>
            </div>

            <div class="mt-3">
                <label>{{ texts.load_name }}</label>
                <input 
                    type="text" 
                    name="load_name" 
                    class="form-control" 
                    value="{{ load_name }}"
                >
                <button type="submit" name="action" value="load" class="btn btn-secondary mt-2">
                    {{ texts.load_button }}
                </button>
            </div>
        </form>
    </div>

    <script>
        function switchLanguage(lang) {
            document.cookie = `lang=${lang};path=/`;
            window.location.reload();
        }
    </script>
</body>
</html>
'''

def parse_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None

def calculate_history_days(entries, last_exit_date):
    """计算最后离境日期前180天的停留天数"""
    if not entries:
        return 0
    
    window_start = last_exit_date - timedelta(days=180)
    total_days = 0
    
    for entry in entries:
        entry_start = max(entry['start'], window_start)
        entry_end = min(entry['end'], last_exit_date)
        
        if entry_end >= entry_start:
            total_days += (entry_end - entry_start).days + 1
            
    # return min(total_days, 90)
    return total_days

def calculate_next_stay(entries, next_entry_date):
    """计算下次入境后的可用天数"""
    window_start = next_entry_date - timedelta(days=180)
    total_days = 0

    for entry in entries:
        entry_start = max(entry['start'], window_start)
        entry_end = min(entry['end'], next_entry_date)
        
        if entry_end >= entry_start:
            total_days += (entry_end - entry_start).days + 1

    return max(90 - total_days, 0)

@app.route('/', methods=['GET', 'POST'])
def index():
    lang = request.cookies.get('lang', 'en')
    texts = LANGUAGES[lang]
    error = None
    load_error = None
    result = None
    travel_dates = ""
    next_entry = ""
    save_name = ""
    load_name = ""
    previous_days = 0
    last_exit_date = "N/A"

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'save':
            # 保存记录逻辑
            save_name = request.form.get('save_name', '')
            if save_name:
                data = {
                    'travel_dates': request.form.get('travel_dates', ''),
                    'next_entry': request.form.get('next_entry', '')
                }
                r.set(save_name, json.dumps(data))
            travel_dates = request.form.get('travel_dates', '')
            next_entry = request.form.get('next_entry', '')
            
        elif action == 'load':
            # 加载记录逻辑
            load_name = request.form.get('load_name', '')
            if load_name:
                data = r.get(load_name)
                if data:
                    data = json.loads(data)
                    travel_dates = data.get('travel_dates', '')
                    next_entry = data.get('next_entry', '')
                else:
                    load_error = texts['error_load']
        else:            
            entries = []
            travel_dates = request.form.get('travel_dates', '')
            next_entry_str = request.form.get('next_entry', '')

            # 解析行程日期
            for line in travel_dates.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                parts = re.split(r'[\t\s]+', line)
                if len(parts) != 2:
                    error = texts['error_date_format']
                    break
                    
                entry_date = parse_date(parts[0])
                exit_date = parse_date(parts[1])
                
                if not entry_date or not exit_date:
                    error = texts['error_date_format']
                    break
                if exit_date < entry_date:
                    error = texts['error_date_order']
                    break
                    
                entries.append({'start': entry_date, 'end': exit_date})

            # 解析下次入境日期
            next_entry_date = parse_date(next_entry_str)
            if not next_entry_date:
                error = error or texts['error_date_format']

            if not error:
                # 获取最后离境日期
                last_exit = max([entry['end'] for entry in entries]) if entries else None
                last_exit_date = last_exit.strftime("%m/%d/%Y") if last_exit else "N/A"
                
                # 计算历史停留天数
                if entries:
                    previous_days = calculate_history_days(entries, last_exit)
                
                # 计算下次可用天数
                result = calculate_next_stay(entries, next_entry_date)
            
            next_entry = next_entry_str

    return render_template_string(HTML_TEMPLATE,
        texts=texts,
        travel_dates=travel_dates,
        next_entry=next_entry,
        error=error,
        load_error=load_error,
        result=result,
        previous_days=previous_days,
        last_exit_date=last_exit_date,
        save_name=save_name,
        load_name=load_name
    )

if __name__ == '__main__':
    app.run(debug=True)