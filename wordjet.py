#!/usr/bin/env python3

from math import sqrt
import os
import random
import sqlite3

from flask import Flask, send_from_directory, jsonify, request, render_template

app = Flask(__name__)

MAIN_FOLDER = os.path.dirname(__file__)
STATIC_FOLDER = os.path.join(os.path.dirname(__file__), 'static')
DATABASE = os.environ.get('DATABASE', 'db.sqlite')


def load_words(fname):
    with open(fname) as f:
        return f.read().splitlines()


def init_db(dbname):
    con = sqlite3.connect(dbname)
    with con:
        con.execute(
                'CREATE TABLE IF NOT EXISTS Scores (word TEXT PRIMARY KEY NOT NULL, up INT NOT NULL, down INT NOT NULL)')
    con.close()


def increase_score(con, word, direction):
    assert direction in ('up', 'down'), f'Direction ({direction}) should be either up or down'
    default_up = 1 if direction == 'up' else 0
    default_down = 1 if direction == 'down' else 0
    with con:
        cur = con.cursor()
        cur.execute(f'''
    INSERT INTO Scores(word, up, down) VALUES(?, ?, ?)
    ON CONFLICT(word) DO UPDATE SET {direction}={direction}+1
    ''', (word, default_up, default_down))
        assert cur.rowcount == 1, cur.rowcount


def read_scores(con, words):
    word_scores = {word: (0, 0) for word in words}
    for word, up, down in  con.cursor().execute('SELECT word, up, down FROM Scores'):
        if word in word_scores:
            word_scores[word] = (up, down)
    return [(word, up, down) for word, (up, down) in word_scores.items()]


def wilson_score(up, down):
    n = up + down
    if n == 0:
        return 0
    z = 1.281551565545
    p = float(down) / n
    left = p + 1/(2*n)*z*z
    right = z*sqrt(p*(1-p)/n + z*z/(4*n*n))
    under = 1+1/n*z*z
    return (left - right) / under


def calculate_weights(words):
    in_flight_cards = 30
    ease_in_turns = 4

    weights = {word: (max(0.01, wilson_score(up, down)), up, down)
               for word, up, down in words}

    new_cards = []
    in_progress_count = 0
    for word, (weight, up, down) in weights.items():
        if up + down == 0:
            new_cards.append(word)
            continue

        if up < ease_in_turns:
            in_progress_count += 1

        if up + down < ease_in_turns:
            # For initial turns, artificially increase the difficulty
            # For example, 0 turns =>1, 1 turn => 0.9, 2 turns => 0.8, etc
            weight = max(weight, 1-(up+down)/ease_in_turns)
            weights[word] = (weight, up, down)

    pick_extra_count = in_flight_cards - in_progress_count
    if pick_extra_count > 0:
        pick_extra_count = min(pick_extra_count, len(new_cards))
        for word in random.sample(new_cards, k=pick_extra_count):
            weight, up, down = weights[word]
            weight = 1
            weights[word] = (weight, up, down)

    return [weights[word][0] for word, _, _ in words]


@app.route('/words', methods=['GET'])
def words():
    num_questions = 50
    con = sqlite3.connect(DATABASE)
    try:
        words = read_scores(con, WORDS)
        weights = calculate_weights(words)
        words = [word for word, _, _ in random.choices(
            words, weights, k=min(num_questions, len(WORDS)))]
        return jsonify(words)
    finally:
        con.close()

@app.route("/response", methods=['POST'])
def mark_response():
    if set(request.json.keys()) != {'word', 'correct'}:
        return 'Invalid request format', 400

    word = request.json['word']
    if word not in WORDS:
        return 'Unknown word %s' % word, 400

    direction = 'up' if request.json['correct'] else 'down'

    con = sqlite3.connect(DATABASE)
    try:
        increase_score(con, word, direction)
        return 'OK', 200
    finally:
        con.close()


def quantize(words):
    total = len(words)
    stats = [0] * 101
    for word, _, _, chance in words:
        assert 0 <= chance <= 100, (word, chance)
        stats[chance] += 1
    return [(cnt, '#' * int(50 * cnt/total)) for cnt in stats]


@app.route('/stats', methods=['GET'])
def stats():
    con = sqlite3.connect(DATABASE)
    try:
        words = read_scores(con, WORDS)
        weights = calculate_weights(words)
        assert len(words) == len(weights), '%d words != %d weights' % (len(words), len(weights))
        words = [(word, up, down, int((1-chance) * 100)) for (word, up, down), chance in zip(words, weights)]
        words.sort(key=lambda w: (w[3], w[1]+w[2], w[1], w[2], w[0]))

        total_good = sum(up for _, up, _, _ in words)
        total_bad = sum(bad for _, _, bad, _ in words)

        return render_template(
                'stats.html',
                words=words,
                total_good=total_good,
                total_bad=total_bad,
                stats=quantize(words))
    finally:
        con.close()


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/favicon.ico', methods=['GET'])
def favicon():
    return send_from_directory(STATIC_FOLDER, 'favicon.ico')

WORDS = load_words(os.path.join(MAIN_FOLDER, 'dictionary.txt'))
init_db(DATABASE)
