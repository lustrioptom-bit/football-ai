def get_sofascore_live():
    """
    Загружает live-матчи с прокси-сервера SofaScore
    """
    import requests
    import logging

    logger = logging.getLogger(__name__)

    # Прокси-сервер, который не блокируется
    url = "https://api-pub.sb.scoreticker.com/api/v1/sport/football/events/live"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': 'https://www.sofascore.com/',
        'Origin': 'https://www.sofascore.com',
        'Sec-Fetch-Site': 'same-origin',
        'Connection': 'keep-alive'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            matches = []
            for event in data.get('events', []):
                try:
                    home = event['homeTeam']['name']
                    away = event['awayTeam']['name']
                    score = f"{event['homeScore']['current']}:{event['awayScore']['current']}"
                    minute = event['minute']
                    status = event['status']['type']
                    
                    if status in ["live", "paused"]:  # Только live-матчи
                        match_data = {
                            'home': home,
                            'away': away,
                            'score': score,
                            'minute': minute,
                            'status': status
                        }
                        # Добавляем xG, если есть
                        if 'xG' in event:
                            match_data['xG_home'] = round(event['xG']['home'], 2)
                            match_data['xG_away'] = round(event['xG']['away'], 2)
                        # Добавляем статистику
                        if 'statistics' in event:
                            for stat in event['statistics']:
                                if stat['type'] == 'possession':
                                    match_data['possession'] = f"{stat['home']}% - {stat['away']}%"
                                elif stat['type'] == 'attacks':
                                    match_data['attacks'] = f"{stat['home']} - {stat['away']}"
                                elif stat['type'] == 'dangerous_attacks':
                                    match_data['danger_attacks'] = f"{stat['home']} - {stat['away']}"
                        matches.append(match_data)
                except KeyError as e:
                    logger.warning(f"Пропущен матч из-за отсутствия данных: {e}")
                    continue
            return matches
        else:
            logger.error(f"❌ Ошибка SofaScore: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"❌ Ошибка запроса к SofaScore: {e}")
        return []
