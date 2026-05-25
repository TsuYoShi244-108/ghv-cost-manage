from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import json
import os
import psycopg2
import psycopg2.extras
from datetime import datetime
import base64
import io
import re
import anthropic
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))

app = Flask(__name__)
CORS(app)

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'goco59h')

HORSES = ['グートアウス', 'レストア', 'ダーク', 'ジェンツ', 'ヨヌィヨ', 'レオラック',
          'キャロシ', 'フォシシ', 'オデイール', 'モルモ', 'ロドシ', 'ネムタロウ',
          'ヴィン', 'ヨテシ', 'ロロ', 'ポボイ', 'ムルシ', 'ムテロ']

DEFAULT_FEED_PRICES = {
    'alfalfa': {'name': 'USアルファルファ1番刈', 'unit': 'kg', 'price': 84.80},
    'timothy': {'name': 'USチモシーラフ', 'unit': 'kg', 'price': 104.00},
    'ryegrass': {'name': 'USライグラスシーズストロー', 'unit': 'kg', 'price': 73.00},
    'bran': {'name': 'ふすま 20kg', 'unit': '袋', 'price': 1460},
    'calcium_phosphate': {'name': 'リンカルシウム', 'unit': 'kg', 'price': 1000},
    'rice_oil': {'name': 'こめ油', 'unit': 'kg', 'price': 800},
    'salt': {'name': '塩', 'unit': 'kg', 'price': 500}
}

MEDICAL_PRICES = {
    'vaccine': {'name': 'ワクチン', 'price': 0},
    'shoeing': {'name': '装蹄（4肢装蹄）', 'price': 16500},
    'trimming': {'name': '削蹄のみ（4肢装蹄）', 'price': 7000},
    'worming': {'name': '駆虫投薬', 'price': 3000}
}


def get_db():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception('DATABASE_URL is not set')
    conn = psycopg2.connect(database_url)
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS monthly_costs (
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            common_costs JSONB DEFAULT '{}'::jsonb,
            horse_costs JSONB DEFAULT '{}'::jsonb,
            feed_prices JSONB DEFAULT '{}'::jsonb,
            PRIMARY KEY (year, month)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key VARCHAR PRIMARY KEY,
            value JSONB NOT NULL
        )
    ''')
    # Insert default feed prices if not exists
    cur.execute('''
        INSERT INTO config (key, value)
        VALUES ('feed_prices', %s::jsonb)
        ON CONFLICT (key) DO NOTHING
    ''', (json.dumps(DEFAULT_FEED_PRICES),))
    conn.commit()
    cur.close()
    conn.close()


def get_feed_prices_from_db():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT value FROM config WHERE key = 'feed_prices'")
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return row['value']
    return DEFAULT_FEED_PRICES


def set_feed_prices_in_db(prices):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO config (key, value)
        VALUES ('feed_prices', %s::jsonb)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    ''', (json.dumps(prices),))
    conn.commit()
    cur.close()
    conn.close()


# Initialize DB on startup
try:
    init_db()
except Exception as e:
    print(f'DB init error: {e}')


@app.route('/')
def index():
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()


@app.route('/api/login', methods=['POST'])
def login():
    password = request.json.get('password')
    if password == ADMIN_PASSWORD:
        return jsonify({'success': True, 'message': 'ログイン成功'})
    return jsonify({'success': False, 'message': 'パスワードが正しくありません'}), 401


@app.route('/api/horses', methods=['GET'])
def get_horses():
    return jsonify({'horses': HORSES})


@app.route('/api/feed-prices', methods=['GET'])
def get_feed_prices():
    prices = get_feed_prices_from_db()
    return jsonify({'prices': prices})


@app.route('/api/month-data/<year>/<month>', methods=['GET'])
def get_month_data(year, month):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        'SELECT common_costs, horse_costs, feed_prices FROM monthly_costs WHERE year = %s AND month = %s',
        (int(year), int(month))
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row:
        return jsonify({
            'common_costs': row['common_costs'],
            'horse_costs': row['horse_costs'],
            'feed_prices': row['feed_prices']
        })

    feed_prices = get_feed_prices_from_db()
    return jsonify({'common_costs': {}, 'horse_costs': {}, 'feed_prices': feed_prices})


@app.route('/api/save-month/<year>/<month>', methods=['POST'])
def save_month(year, month):
    payload = request.json
    common_costs = payload.get('common_costs', {})
    horse_costs = payload.get('horse_costs', {})
    feed_prices = payload.get('feed_prices', {})

    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO monthly_costs (year, month, common_costs, horse_costs, feed_prices)
        VALUES (%s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
        ON CONFLICT (year, month) DO UPDATE SET
            common_costs = EXCLUDED.common_costs,
            horse_costs = EXCLUDED.horse_costs,
            feed_prices = EXCLUDED.feed_prices
    ''', (int(year), int(month),
          json.dumps(common_costs),
          json.dumps(horse_costs),
          json.dumps(feed_prices)))
    conn.commit()
    cur.close()
    conn.close()

    if feed_prices:
        set_feed_prices_in_db(feed_prices)

    key = f'{year}-{int(month):02d}'
    return jsonify({'success': True, 'message': 'データ保存完了', 'key': key})


@app.route('/api/report/<year>', methods=['GET'])
def get_year_report(year):
    report = {
        'year': year,
        'total_cost': 0,
        'monthly_breakdown': {},
        'horse_ranking': {},
        'cost_by_category': {}
    }

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        'SELECT month, common_costs, horse_costs FROM monthly_costs WHERE year = %s',
        (int(year),)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    for row in rows:
        month = row['month']
        month_total = 0

        if row['common_costs']:
            for category, items in row['common_costs'].items():
                if isinstance(items, dict):
                    for item_name, cost in items.items():
                        month_total += cost

        if row['horse_costs']:
            for horse, costs in row['horse_costs'].items():
                if isinstance(costs, dict):
                    for category, cost in costs.items():
                        month_total += cost

        report['monthly_breakdown'][f'{month}月'] = month_total
        report['total_cost'] += month_total

    return jsonify(report)


@app.route('/api/receipt/analyze', methods=['POST'])
def analyze_receipt():
    if 'image' not in request.files:
        return jsonify({'error': '画像ファイルが必要です'}), 400

    file = request.files['image']
    image_data = file.read()
    base64_image = base64.b64encode(image_data).decode('utf-8')

    content_type = file.content_type or 'image/jpeg'
    if content_type not in ('image/jpeg', 'image/png', 'image/gif', 'image/webp'):
        content_type = 'image/jpeg'

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY が設定されていません'}), 500

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=512,
        messages=[
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': content_type,
                            'data': base64_image,
                        },
                    },
                    {
                        'type': 'text',
                        'text': (
                            'このレシート画像から以下の情報を読み取り、必ずJSON形式だけで返してください。'
                            '余分なテキストは一切含めないでください。\n'
                            '{\n'
                            '  "timestamp": "日付と時刻（例: 2024年1月15日 14:30）",\n'
                            '  "amount": "合計金額（数字のみ、例: 1250）",\n'
                            '  "company": "企業名・会社名",\n'
                            '  "store": "店舗名・支店名"\n'
                            '}\n'
                            '読み取れないフィールドは空文字列にしてください。'
                        ),
                    },
                ],
            }
        ],
    )

    response_text = message.content[0].text.strip()
    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            data = {'timestamp': '', 'amount': '', 'company': '', 'store': ''}
    else:
        data = {'timestamp': '', 'amount': '', 'company': '', 'store': ''}

    return jsonify(data)


@app.route('/api/receipt/pdf', methods=['POST'])
def generate_receipt_pdf():
    data = request.json or {}
    timestamp = data.get('timestamp', '')
    amount = data.get('amount', '')
    company = data.get('company', '')
    store = data.get('store', '')

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font = 'HeiseiKakuGo-W5'

    # ヘッダー背景
    c.setFillColor(colors.HexColor('#2c3e50'))
    c.rect(0, height - 100, width, 100, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont(font, 22)
    c.drawString(50, height - 55, 'レシート情報')
    c.setFont(font, 11)
    c.drawString(50, height - 80, '読み取り結果')

    # 区切り線
    c.setStrokeColor(colors.HexColor('#ecf0f1'))
    c.setLineWidth(1)
    c.line(50, height - 120, width - 50, height - 120)

    fields = [
        ('日時', timestamp or '（不明）'),
        ('企業名', company or '（不明）'),
        ('店舗名', store or '（不明）'),
        ('金額', f'¥{int(amount):,}' if amount and str(amount).isdigit() else (f'¥{amount}' if amount else '（不明）')),
    ]

    label_x = 60
    value_x = 180
    y = height - 165
    row_height = 60

    for label, value in fields:
        # 行背景
        c.setFillColor(colors.HexColor('#f8f9fa'))
        c.rect(40, y - 12, width - 80, 44, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor('#dee2e6'))
        c.setLineWidth(0.5)
        c.rect(40, y - 12, width - 80, 44, fill=0, stroke=1)

        c.setFillColor(colors.HexColor('#6c757d'))
        c.setFont(font, 10)
        c.drawString(label_x, y + 18, label)

        c.setFillColor(colors.HexColor('#212529'))
        c.setFont(font, 14)
        c.drawString(value_x, y + 15, value)

        y -= row_height

    # フッター
    c.setFillColor(colors.HexColor('#f8f9fa'))
    c.rect(0, 0, width, 40, fill=1, stroke=0)
    c.setFillColor(colors.HexColor('#adb5bd'))
    c.setFont(font, 9)
    generated_at = datetime.now().strftime('%Y年%m月%d日 %H:%M')
    c.drawString(50, 14, f'作成日時: {generated_at}')

    c.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name='receipt.pdf',
        mimetype='application/pdf',
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
