import sys
import requests
import yaml
import pytz
import time
from argparse import ArgumentParser
from datetime import datetime, timedelta

BASE_URL = 'https://portal.ufsm.br/mobile/webservice/flutter'

def read_config() -> dict:
    with open('config.yaml', 'r') as document:
        return yaml.safe_load(document)

def is_weekday(date: datetime, weekday: str) -> bool:
    return date.strftime('%a') == weekday

def resolve_restaurant_id(restaurant: int):
    match restaurant:
        case 2:
            return 41
        case _:
            return restaurant

def login(username: str, password: str) -> str:
    for tentativa in range(3):
        try:
            response = requests.post(
                f'{BASE_URL}/generateTokenJwt',
                json={
                    'appName': config['environment']['app'],
                    'deviceId': config['environment']['device-id'],
                    'deviceInfo': config['environment']['device-info'],
                    'messageToken': config['environment']['message-token'],
                    'login': username,
                    'senha': password,
                },
                headers={
                    'User-Agent': 'Dart/3.12 (dart:io)',
                    'x-ufsm-version': '50600',
                    'Content-Type': 'application/json; charset=UTF-8'
                },
                timeout=20
            )
            data = response.json()
            if data['error']:
                raise Exception(data.get('mensagem', 'Erro no login'))
            return data['body']['accessToken']
        except requests.exceptions.RequestException as e:
            print(f"Tentativa {tentativa + 1}/3 falhou: {e}")
            if tentativa == 2:
                raise
            time.sleep(10)

def schedule_meal(token: str, start: datetime, end: datetime, options: dict) -> list:
    payload = {
        'dataInicio': start.strftime('%Y-%m-%d %H:%M:%S'),
        'dataFim': end.strftime('%Y-%m-%d %H:%M:%S'),
        'idRestaurante': resolve_restaurant_id(options['restaurant']),
        'opcaoVegetariana': options['vegetarian'],
        'tiposRefeicoes': []
    }

    # O payload precisou ser substituído por um int()
    if options['coffee']:
        payload['tiposRefeicoes'].append(1)

    if options['lunch']:
        payload['tiposRefeicoes'].append(2)

    if options['dinner']:
        payload['tiposRefeicoes'].append(3)

    response = requests.post(
        f'{BASE_URL}/ru/agendaRefeicoes',
        json=payload,
        headers={
            'User-Agent': 'Dart/3.12 (dart:io)',
            'x-ufsm-version': '50600',
            'X-UFSM-Device-ID': config['environment']['device-id'],
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json; charset=UTF-8'
        }
    )
    return response.json()['body']

def find_schedules(date):
    filtered_schedules = filter(
        lambda s : is_weekday(date, s['weekday']),
        config['schedules']
    )

    return list(filtered_schedules)

parser = ArgumentParser(
    prog='ruina',
    description='Agenda automaticamente as refeições do RU da UFSM.'
)

parser.add_argument('-u --username', dest='username', help='Sua matrícula do aplicativo da UFSM.')
parser.add_argument('-p --password', dest='password', help='Sua senha do aplicativo da UFSM.')

args = parser.parse_args()

print('Lendo configuração...')
config = read_config()

print('Procurando refeições para serem agendadas amanhã...')
now = datetime.now(pytz.timezone('Brazil/East'))
tomorrow = now + timedelta(1)

tomorrow_schedules = find_schedules(tomorrow)

if len(tomorrow_schedules) != 0:
    print(f'Encontrado {len(tomorrow_schedules)} refeição(s) para serem agendadas.')

    try:
        print('Logando no aplicativo...')
        access_token = login(args.username, args.password)
    except Exception as exception:
        print(f'Falha ao logar: {str(exception)}')
        sys.exit(1)
    else:
        failed = False

        for schedule in tomorrow_schedules:
            print(f"Agendando refeições para o RU {schedule['restaurant']}... ({schedule})")

            statuses = schedule_meal(access_token, tomorrow, tomorrow, schedule)

            for status in statuses:
                date = datetime.strptime(status['dataRefAgendada'], '%Y-%m-%d %H:%M:%S')
                message = (
                    f"{date.strftime('%d/%m/%Y')} - "
                    f"RU {schedule['restaurant']} ({status['tipoRefeicao']}): "
                )

                if status['sucesso']:
                    print(message + 'Agendado com sucesso.')
                else:
                    impedimento = status.get('impedimento', 'Erro desconhecido')
                
                    if impedimento == 'Já existe um agendamento com estes dados':
                        print(message + 'Já estava agendado.')
                    else:
                        print('[Erro] ' + message + impedimento + '.')
                        failed = True

        if failed:
            sys.exit(1)
else:
    print('Não há nenhuma refeição para ser agendada amanhã.')
