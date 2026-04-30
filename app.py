from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# データ保存先
DATA_FILE = 'horse_cost_data.json'

# パスワード（環境変数から取得、なければデフォルト）
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'gocoo59h')

# 馬リスト
HORSES = ['グートアウス', 'レストア', 'ダーク', 'ステップ', 'ジュジュ', 'ロアッソ', 
          'カラス', 'ミライ', 'オディール', 'メルモ', 'ラピス', 'マサゴロウ', 
          'ジン', 'シュン', 'ララ', 'ポテト', 'マルコ', 'ユメ']

# デフォルト飼料単価（2026年3月時点）
DEFAULT_FEED_PRICES = {
    'hay_cube': {'name': 'ヘイキューブ 30kg', 'unit': '袋', 'price': 3970},
    'bran': {'name': 'ふすま 20kg', 'unit': '袋', 'price': 1460},
    'timothy': {'name': 'USチモシープレ', 'unit': 'kg', 'price': 104.00},
    'alfalfa': {'name': 'USアルファ1番刈', 'unit': 'kg', 'price': 84.80},
    'ryegrass': {'name': 'USライグラス・ストロー', 'unit': 'kg', 'price': 73.00},
    'barley': {'name': '皮つき圧ぺん麦 20kg', 'unit': '袋', 'price': 1601},
    'high_horse': {'name': 'ハイホス 20kg', 'unit': '袋', 'price': 4540},
    'salt': {'name': '塩', 'unit': 'kg', 'price': 500},
    'rice_oil': {'name': 'こめ油', 'unit': 'kg', 'price': 800},
    'calcium_phosphate': {'name': 'リン酸カルシウム', 'unit': 'kg', 'price': 1000}
}

# 医療費の相場（2026年時点 税抜き）
MEDICAL_PRICES = {
    'vaccine': {'name': 'ワクチン', 'price': 0},
    'shoeing': {'name': '装蹄（4本脚）', 'price': 16500},
    'trimming': {'name': '削蹄のみ（4本脚）', 'price': 7000},
    'worming': {'name': '駆虫薬', 'price': 3000}
}

def load_data():
    """データを読み込む"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {'records': {}, 'feed_prices': DEFAULT_FEED_PRICES}
    return {'records': {}, 'feed_prices': DEFAULT_FEED_PRICES}

def save_data(data):
    """データを保存"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route('/')
def index():
    """HTMLを返す"""
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/api/login', methods=['POST'])
def login():
    """ログイン"""
    password = request.json.get('password')
    if password == ADMIN_PASSWORD:
        return jsonify({'success': True, 'message': 'ログイン成功'})
    return jsonify({'success': False, 'message': 'パスワードが違います'}), 401

@app.route('/api/horses', methods=['GET'])
def get_horses():
    """馬リスト取得"""
    return jsonify({'horses': HORSES})

@app.route('/api/feed-prices', methods=['GET'])
def get_feed_prices():
    """飼料単価取得"""
    data = load_data()
    return jsonify({'prices': data['feed_prices']})

@app.route('/api/month-data/<year>/<month>', methods=['GET'])
def get_month_data(year, month):
    """月別データ取得"""
    data = load_data()
    key = f'{year}-{int(month):02d}'
    if key in data['records']:
        return jsonify(data['records'][key])
    return jsonify({'common_costs': {}, 'horse_costs': {}, 'feed_prices': data['feed_prices']})

@app.route('/api/save-month/<year>/<month>', methods=['POST'])
def save_month(year, month):
    """月別データ保存"""
    data = load_data()
    key = f'{year}-{int(month):02d}'
    
    payload = request.json
    data['records'][key] = payload
    
    # 飼料単価を更新（翌月用）
    if 'feed_prices' in payload:
        data['feed_prices'] = payload['feed_prices']
    
    save_data(data)
    return jsonify({'success': True, 'message': 'データ保存完了', 'key': key})

@app.route('/api/report/<year>', methods=['GET'])
def get_year_report(year):
    """年間レポート取得"""
    data = load_data()
    report = {
        'year': year,
        'total_cost': 0,
        'monthly_breakdown': {},
        'horse_ranking': {},
        'cost_by_category': {}
    }
    
    # 月ごとのデータを集計
    for month in range(1, 13):
        key = f'{year}-{int(month):02d}'
        if key in data['records']:
            month_data = data['records'][key]
            month_total = 0
            
            # 共通費の集計
            if 'common_costs' in month_data:
                for category, items in month_data['common_costs'].items():
                    for item_name, cost in items.items():
                        month_total += cost
            
            # 馬別追加費の集計
            if 'horse_costs' in month_data:
                for horse, costs in month_data['horse_costs'].items():
                    for category, cost in costs.items():
                        month_total += cost
            
            report['monthly_breakdown'][f'{month}月'] = month_total
            report['total_cost'] += month_total
    
    return jsonify(report)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
