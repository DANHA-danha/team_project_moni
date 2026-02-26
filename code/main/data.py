import os
import time
import json
import pandas as pd
import random
import google.generativeai as genai
from datetime import datetime, timedelta, time as dt_time
from .models import Spending, BankAccount
import joblib
from django.utils import timezone
from django.db.models import Q
from .views import _helpers


START_DATE = timezone.make_aware(datetime(2024, 1, 1))
END_DATE = timezone.now()

# 소비내역 생성
MERCHANTS_DB = {
    # [1] 식사 (4단계 등급)
    'food_cheap': ['GS25', 'CU', '세븐일레븐', '김밥천국', '이삭토스트', '봉구스밥버거', '한솥도시락', '명랑핫도그', '파리바게트'],
    'food_middle': ['순대국', '김치찌개', '맘스터치', '롯데리아', '홍콩반점', '미소야', '서브웨이', '김가네', '역전우동', '맥도날드', '본죽', '돈까스'],
    'food_expensive': ['아웃백', '빕스', '하이디라오', '역전할머니맥주', '이자카야', '곱창', '매드포갈릭', '교촌치킨(매장)', '삼겹살맛집'],
    'food_luxury': ['스시오마카세', '한우오마카세', '정식당', '신라호텔더파크뷰', '울프강스테이크', '롯데호텔라세느'],

    # [2] 카페
    'cafe_cheap': ['메가커피', '컴포즈커피', '빽다방', '매머드커피', '더벤티', 'GS25', 'CU', '세븐일레븐', '이디야'],
    'cafe_expensive': ['스타벅스', '블루보틀', '폴바셋', '투썸플레이스', '테라로사', '감성개인카페', '할리스', '엔제리너스', '커피빈'],

    # [3] 교통/차량
    'transport_public': ['지하철', '버스', '광역버스', '마을버스', '티머니'],
    'transport_taxi': ['카카오택시', '우티(UT)', '타다', '지역콜택시', '모범택시'],
    'car_fuel': ['GS칼텍스', 'SK엔크린', 'S-OIL', 'HD현대오일뱅크', '알뜰주유소'],
    'car_service': ['삼성화재다이렉트', '타이어프로', '손세차장', '자동차검사소'],
    'car_rent': ['쏘카', '그린카', '롯데렌터카', '제주렌트카'],

    # [구독 1] 미디어/엔터테인먼트 (영상, 음악, 도서, 게임)
    'subscription_media': [
        # 영상 (OTT)
        '넷플릭스', '유튜브프리미엄', '디즈니플러스', '티빙', '웨이브', '왓챠', 'AppleTV+', '라프텔(애니)',
        # 음악
        '멜론', '지니뮤직', '스포티파이', '유튜브뮤직', 'AppleMusic', 'FLO(플로)', 'VIBE(바이브)', '벅스',
        # 도서/웹툰
        '밀리의서재', '리디셀렉트', 'Yes24크레마클럽', '네이버웹툰(쿠키)',
        # 게임
        'Xbox_GamePass', 'PlayStation_Plus', 'Nintendo_Online'],

    # [구독 2] 업무/생산성 (클라우드, 개발, 디자인, 협업)
    'subscription_work': [
        # 일반 사무/생성형 AI
        'MS_Office365', 'ChatGPT_Plus', 'Notion_Plus', 'Evernote', 'Grammarly',
        # 디자인/창작
        'Adobe_Creative_Cloud', 'Canva_Pro', 'Figma_Pro', 'Midjourney',
        # 개발/IT
        'GitHub_Copilot', 'JetBrains_All_Products', 'AWS(FreeTier_Over)',
        # 클라우드/협업
        'Google_One', 'iCloud_Plus', 'Dropbox_Plus', 'Slack_Pro', 'Zoom_Pro'],

    # [구독 3] 생활/쇼핑 멤버십
    'subscription_life': [
        # 쇼핑
        '쿠팡와우멤버십', '네이버플러스멤버십', '신세계유니버스', '마켓컬리패스', '스마일클럽',
        # 배달/통신/기타
        '요기요패스', '배민클럽', 'T우주패스'],

    # [5] 금융 (고정비/자산형성)
    'finance_savings': ['주택청약저축', '카카오뱅크', '토스뱅크', '신한은행', '국민은행'],
    'finance_invest': ['키움증권', '토스증권', '업비트', '미래에셋증권'],
    'finance_insurance': ['삼성화재(실비)', '현대해상', 'DB손해보험', '메리츠화재', '라이나생명'],
    'finance_loan': ['한국장학재단', '버팀목전세이자', '주택담보대출이자', '신용대출이자'],

    # [6] 이벤트/취미
    'travel_domestic': ['코레일', '제주항공', '대한항공', '아시아나', '야놀자', 'AirBnB'],
    'travel_overseas': ['대한항공', '아시아나', '익스피디아', '아고다', '트립닷컴', '해외결제(Visa)', 'AirBnB'],
    'shopping_tech': ['Apple_Store', '삼성스토어', '하이마트', '일렉트로마트', '프리스비'],
    'hobby_active': ['헬스장', '필라테스', '실내클라이밍', '테니스장', '골프연습장', '볼링장'],
    'hobby_creative': ['원데이클래스', '가죽공방', '성인피아노', '도자기공방', '화실'],

    # [7] 일상/생활
    'shopping_online': ['쿠팡', '무신사', '지그재그', '네이버페이', '에이블리', '마켓컬리'],
    'shopping_luxury': ['신세계백화점', '현대백화점', '성수동편집샵', '명품관'],
    'delivery': ['배달의민족', '요기요', '쿠팡이츠'],
    'household': ['다이소', '동네식자재마트', '크린토피아', '올리브영(생필품)'],
    'baby_living': ['쿠팡(육아)', '이마트', '한샘', '베이비플러스', '소아과', '키즈카페'],
    'study_job': ['해커스', '스터디카페', '독서실', '교보문고', '패스트캠퍼스'],
    'medical_cure': ['내과', '이비인후과', '정형외과', '약국', '치과', '안과'],
    'medical_beauty': ['피부과', '성형외과', '비만클리닉', '치과(교정)', '에스테틱'],
    'living': ['SKT/KT/LGU+', '한국전력', '도시가스', '부동산(월세)', '관리비', '건강보험공단']
}

SUBSCRIPTION_PRICES = {
    # --- [미디어: 영상] ---
    '넷플릭스': 17000,  # 프리미엄
    '유튜브프리미엄': 14900, '디즈니플러스': 9900,  # 스탠다드
    '티빙': 13500,  # 스탠다드
    '웨이브': 10900, '왓챠': 12900, 'AppleTV+': 6500, '라프텔(애니)': 9900,

    # --- [미디어: 음악] ---
    '멜론': 10900,  # 스트리밍 클럽
    '지니뮤직': 8400, '스포티파이': 10900,  # 개인
    '유튜브뮤직': 11900,  # 뮤직 프리미엄 단독
    'AppleMusic': 8900, 'FLO(플로)': 11000, 'VIBE(바이브)': 8500, '벅스': 12000,

    # --- [미디어: 도서/게임] ---
    '밀리의서재': 9900, '리디셀렉트': 4900, 'Yes24크레마클럽': 5500, '네이버웹툰(쿠키)': 10000,  # 정기충전 가정
    'Xbox_GamePass': 13500,  # 얼티밋
    'PlayStation_Plus': 11000,  # 스페셜 (월할 환산)
    'Nintendo_Online': 4900,

    # --- [업무: 디자인/개발/클라우드] ---
    'Adobe_Creative_Cloud': 62000, 'Canva_Pro': 14000, 'Figma_Pro': 20000,  # $15 환산
    'Midjourney': 13000,  # Basic Plan
    'GitHub_Copilot': 14000,  # $10 환산
    'JetBrains_All_Products': 35000,
    'AWS(FreeTier_Over)': 50000,  # 초과 과금 평균 가정
    'Google_One': 11900,  # 2TB
    'iCloud_Plus': 4400,  # 200GB
    'Dropbox_Plus': 14000, 'Slack_Pro': 11000, 'Zoom_Pro': 20000,

    # --- [업무: 사무/AI] ---
    'MS_Office365': 11900,  # Personal
    'ChatGPT_Plus': 29000,  # $20 환산
    'Notion_Plus': 11000, 'Evernote': 10000, 'Grammarly': 16000,

    # --- [생활: 쇼핑/배달] ---
    '쿠팡와우멤버십': 7890, '네이버플러스멤버십': 4900,
    '신세계유니버스': 2500,  # 연회비 월할 계산 or 프로모션
    '마켓컬리패스': 4500, '스마일클럽': 3000, '요기요패스': 2900, '배민클럽': 3990, 'T우주패스': 9900
}

# 페르소나 정의 (7가지 유형)
PERSONAS = {

    '일반대학생': {
        'asset_range': (500000, 3000000), 'income_amount': (400000, 1000000), 'pay_day': 1, 'pay_day_type': 'fixed',
        'financial_config': {'finance_savings': {'count': (1, 1), 'amt': (50000, 100000)},
                             'finance_invest': {'count': (0, 1), 'amt': (50000, 100000)}},
        'subs_config': {'media': {'pool': ['넷플릭스', '유튜브프리미엄', '디즈니플러스', '티빙', '웨이브', '왓챠', 'AppleTV+', '라프텔(애니)'],
                                  'count': (1, 3)}},
        'event_config': {'tech_prob': 0.3, 'tech_budget': (800000, 1500000), 'travel_count': (0, 1),
                         'travel_type': 'domestic', 'travel_budget': (200000, 500000)},

        'weights': {
            'transport_public': 25, 'food_cheap': 20, 'shopping_online': 10, 'cafe_cheap': 20,
            'transport_taxi': 5, 'car_fuel': 0, 'car_service': 0, 'car_rent': 0,
            'food_middle': 15, 'food_expensive': 5, 'food_luxury': 5, 'cafe_expensive': 10,
            'shopping_luxury': 0, 'shopping_tech': 0, 'delivery': 5, 'household': 0,
            'baby_living': 0, 'study_job': 15, 'medical_cure': 5, 'medical_beauty': 10,
            'living': 5, 'culture': 5, 'hobby_active': 3, 'hobby_creative': 2,
            'travel_domestic': 1, 'travel_overseas': 0
        },
        'amt_range': {
            'transport_public': (1400, 2800), 'food_cheap': (4500, 6000),
            'shopping_online': (15000, 50000), 'cafe_cheap': (1500, 4500),
            'transport_taxi': (5000, 15000), 'car_fuel': (30000, 50000), 'car_service': (50000, 100000),
            'car_rent': (50000, 100000),
            'food_middle': (8000, 16000), 'food_expensive': (30000, 50000), 'food_luxury': (100000, 200000),
            'cafe_expensive': (5000, 15000),
            'shopping_luxury': (50000, 100000), 'shopping_tech': (100000, 500000),
            'delivery': (15000, 35000), 'household': (5000, 20000), 'baby_living': (30000, 100000),
            'study_job': (5000, 150000),
            'medical_cure': (5000, 20000), 'medical_beauty': (50000, 150000), 'living': (50000, 100000),
            'culture': (10000, 35000), 'hobby_active': (5000, 50000), 'hobby_creative': (50000, 150000),
            'travel_domestic': (100000, 300000), 'travel_overseas': (500000, 1500000)
        }
    },


    '자취대학생': {
        'asset_range': (700000, 2000000), 'income_amount': (800000, 1500000), 'pay_day': 1, 'pay_day_type': 'fixed',
        'financial_config': {'finance_loan': {'count': (0, 1), 'amt': (50000, 100000)},
                             'finance_invest': {'count': (0, 1), 'amt': (10000, 50000)}},
        'subs_config': {
            'media': {'pool': ['넷플릭스', '유튜브프리미엄', '디즈니플러스', '티빙', '웨이브', '왓챠', 'AppleTV+', '라프텔(애니)'], 'count': (0, 1)},
            'life': {'pool': ['쿠팡와우멤버십', '배민클럽'], 'count': (1, 2)}},
        'event_config': {'tech_prob': 0.2, 'tech_budget': (500000, 1000000), 'travel_count': (0, 1),
                         'travel_type': 'domestic', 'travel_budget': (200000, 500000)},

        'weights': {
            'transport_public': 5, 'transport_taxi': 1,
            'food_cheap': 20, 'food_middle': 15, 'food_expensive': 3, 'food_luxury': 1,
            'cafe_cheap': 20, 'cafe_expensive': 5,
            'car_fuel': 0, 'car_service': 0, 'car_rent': 0,
            'shopping_online': 10, 'shopping_luxury': 0, 'shopping_tech': 0,
            'delivery': 15, 'household': 15, 'study_job': 15,
            'medical_cure': 10, 'medical_beauty': 0, 'living': 10,
            'culture': 5, 'hobby_active': 3, 'hobby_creative': 2,
            'travel_domestic': 1, 'travel_overseas': 0, 'baby_living': 0,
        },
        'amt_range': {
            'transport_public': (1400, 2800), 'transport_taxi': (5000, 15000),
            'food_cheap': (4500, 6000), 'food_middle': (8000, 16000), 'food_expensive': (30000, 50000),
            'food_luxury': (100000, 200000),
            'cafe_cheap': (1500, 4500), 'cafe_expensive': (5000, 15000),
            'car_fuel': (30000, 50000), 'car_service': (50000, 100000), 'car_rent': (50000, 100000),
            'shopping_online': (15000, 50000), 'shopping_luxury': (50000, 100000), 'shopping_tech': (100000, 500000),
            'delivery': (15000, 35000), 'household': (5000, 20000), 'study_job': (5000, 150000),
            'medical_cure': (5000, 20000), 'medical_beauty': (50000, 150000), 'living': (50000, 150000),
            'culture': (10000, 35000), 'hobby_active': (5000, 50000), 'hobby_creative': (50000, 150000),
            'travel_domestic': (100000, 300000), 'travel_overseas': (500000, 1500000), 'baby_living': (30000, 100000),
        }
    },

    # ------------------------------------------------------------------
    # ③ [20대] 취준생 (초긴축)
    # ------------------------------------------------------------------
    '취준생': {
        'asset_range': (500000, 3000000), 'income_amount': (300000, 800000), 'pay_day_type': 'random',
        'financial_config': {'finance_loan': {'count': (1, 1), 'amt': (30000, 50000)}},
        'subs_config': {'media': {'pool': ['유튜브프리미엄'], 'count': (0, 1)}},
        'event_config': {'tech_prob': 0.05, 'tech_budget': (500000, 800000), 'travel_count': (0, 0)},

        'weights': {
            'transport_public': 15, 'transport_taxi': 1,
            'food_cheap': 30, 'food_middle': 10, 'food_expensive': 3, 'food_luxury': 1,
            'cafe_cheap': 25, 'cafe_expensive': 5,
            'car_fuel': 0, 'car_service': 0, 'car_rent': 0,
            'shopping_online': 5, 'shopping_luxury': 0, 'shopping_tech': 0,
            'delivery': 5, 'household': 15, 'study_job': 15,
            'medical_cure': 10, 'medical_beauty': 0, 'living': 10,
            'culture': 5, 'hobby_active': 0, 'hobby_creative': 0,
            'travel_domestic': 1, 'travel_overseas': 0, 'baby_living': 0,
        },
        'amt_range': {
            'transport_public': (1400, 2800), 'transport_taxi': (5000, 15000),
            'food_cheap': (4500, 6000), 'food_middle': (8000, 16000), 'food_expensive': (30000, 50000),
            'food_luxury': (100000, 200000),
            'cafe_cheap': (1500, 4500), 'cafe_expensive': (5000, 15000),
            'car_fuel': (30000, 50000), 'car_service': (50000, 100000), 'car_rent': (50000, 100000),
            'shopping_online': (15000, 50000), 'shopping_luxury': (50000, 100000), 'shopping_tech': (100000, 500000),
            'delivery': (15000, 35000), 'household': (5000, 20000), 'study_job': (5000, 150000),
            'medical_cure': (5000, 20000), 'medical_beauty': (50000, 150000), 'living': (50000, 150000),
            'culture': (10000, 35000), 'hobby_active': (5000, 50000), 'hobby_creative': (50000, 150000),
            'travel_domestic': (100000, 300000), 'travel_overseas': (500000, 1500000), 'baby_living': (30000, 100000),
        }
    },


    '일반직장인': {
        'asset_range': (25000000, 80000000), 'income_amount': (2500000, 4500000), 'pay_day': 25,
        'pay_day_type': 'fixed',
        'financial_config': {'finance_savings': {'count': (1, 2), 'amt': (300000, 1000000)},
                             'finance_insurance': {'count': (1, 2), 'amt': (100000, 150000)},
                             'finance_invest': {'count': (0, 2), 'amt': (100000, 500000)}},
        'subs_config': {
            'media': {'pool': ['넷플릭스', '유튜브프리미엄', '디즈니플러스', '티빙', '웨이브', '왓챠', 'AppleTV+', '라프텔(애니)'], 'count': (0, 3)},
            'life': {'pool': ['쿠팡와우멤버십', '네이버플러스멤버십', '신세계유니버스', '마켓컬리패스', '요기요패스', '배민클럽', 'T우주패스'], 'count': (0, 3)}},
        'event_config': {'tech_prob': 0.5, 'tech_budget': (500000, 1500000), 'travel_count': (0, 2),
                         'travel_type': 'overseas', 'travel_budget': (500000, 1500000)},

        'weights': {
            'transport_public': 20, 'transport_taxi': 10,
            'food_cheap': 15, 'food_middle': 25, 'food_expensive': 5, 'food_luxury': 5,
            'cafe_cheap': 15, 'cafe_expensive': 15,
            'car_fuel': 10, 'car_service': 10, 'car_rent': 5,
            'shopping_online': 20, 'shopping_luxury': 5, 'shopping_tech': 5,
            'delivery': 20, 'household': 20, 'study_job': 5,
            'medical_cure': 10, 'medical_beauty': 5, 'living': 10,
            'culture': 10, 'hobby_active': 10, 'hobby_creative': 10,
            'travel_domestic': 5, 'travel_overseas': 0, 'baby_living': 0,
        },
        'amt_range': {
            'transport_public': (1400, 2800), 'transport_taxi': (5000, 15000),
            'food_cheap': (4500, 6000), 'food_middle': (8000, 16000), 'food_expensive': (30000, 50000),
            'food_luxury': (100000, 200000),
            'cafe_cheap': (1500, 4500), 'cafe_expensive': (5000, 15000),
            'car_fuel': (30000, 50000), 'car_service': (50000, 100000), 'car_rent': (50000, 100000),
            'shopping_online': (15000, 50000), 'shopping_luxury': (50000, 100000), 'shopping_tech': (100000, 500000),
            'delivery': (15000, 35000), 'household': (10000, 50000), 'study_job': (5000, 150000),
            'medical_cure': (5000, 20000), 'medical_beauty': (50000, 150000), 'living': (50000, 150000),
            'culture': (10000, 35000), 'hobby_active': (5000, 50000), 'hobby_creative': (50000, 150000),
            'travel_domestic': (100000, 300000), 'travel_overseas': (500000, 1500000), 'baby_living': (30000, 100000),
        }
    },


    '전문직': {
        'asset_range': (30000000, 150000000), 'income_amount': (6000000, 10000000), 'pay_day': 21,
        'pay_day_type': 'fixed',
        'financial_config': {'finance_savings': {'count': (1, 2), 'amt': (500000, 1000000)},
                             'finance_insurance': {'count': (1, 2), 'amt': (100000, 150000)},
                             'finance_invest': {'count': (2, 3), 'amt': (2000000, 5000000)}},
        'subs_config': {'media': {'pool': ['넷플릭스', '티빙', '디즈니플러스'], 'count': (2, 3)}},
        'event_config': {'tech_prob': 0.8, 'tech_budget': (2500000, 5000000), 'travel_count': (2, 3),
                         'travel_type': 'overseas', 'travel_budget': (3000000, 7000000)},

        'weights': {
            'transport_public': 15, 'transport_taxi': 10,
            'food_cheap': 10, 'food_middle': 20, 'food_expensive': 10, 'food_luxury': 5,
            'cafe_cheap': 15, 'cafe_expensive': 20,
            'car_fuel': 15, 'car_service': 10, 'car_rent': 0,
            'shopping_online': 20, 'shopping_luxury': 15, 'shopping_tech': 10,
            'delivery': 20, 'household': 20, 'study_job': 5,
            'medical_cure': 10, 'medical_beauty': 15, 'living': 15,
            'culture': 15, 'hobby_active': 15, 'hobby_creative': 15,
            'travel_domestic': 5, 'travel_overseas': 0, 'baby_living': 0,
        },
        'amt_range': {
            'transport_public': (1400, 2800), 'transport_taxi': (5000, 15000),
            'food_cheap': (4500, 6000), 'food_middle': (8000, 16000), 'food_expensive': (30000, 50000),
            'food_luxury': (100000, 300000),
            'cafe_cheap': (1500, 4500), 'cafe_expensive': (5000, 30000),
            'car_fuel': (50000, 150000), 'car_service': (150000, 250000), 'car_rent': (50000, 100000),
            'shopping_online': (50000, 500000), 'shopping_luxury': (250000, 1000000), 'shopping_tech': (100000, 500000),
            'delivery': (15000, 35000), 'household': (5000, 20000), 'study_job': (5000, 150000),
            'medical_cure': (5000, 20000), 'medical_beauty': (50000, 150000), 'living': (50000, 150000),
            'culture': (10000, 50000), 'hobby_active': (30000, 150000), 'hobby_creative': (50000, 150000),
            'travel_domestic': (100000, 300000), 'travel_overseas': (500000, 1500000), 'baby_living': (30000, 100000),
        }
    },

    '신혼육아': {
        'asset_range': (60000000, 150000000), 'income_amount': (4000000, 6000000), 'pay_day': 25,
        'pay_day_type': 'fixed',
        'financial_config': {'finance_loan': {'count': (1, 1), 'amt': (800000, 2000000)},
                             'finance_insurance': {'count': (2, 3), 'amt': (200000, 500000)},
                             'finance_invest': {'count': (0, 3), 'amt': (150000, 500000)}},
        'subs_config': {'life': {'pool': ['쿠팡와우멤버십', '네이버플러스멤버십', '신세계유니버스'], 'count': (2, 3)}},
        'event_config': {'tech_prob': 0.2, 'tech_budget': (1000000, 2000000), 'travel_count': (1, 2),
                         'travel_type': 'domestic', 'travel_budget': (500000, 1000000)},

        'weights': {
            'transport_public': 5, 'transport_taxi': 15,
            'food_cheap': 10, 'food_middle': 20, 'food_expensive': 10, 'food_luxury': 5,
            'cafe_cheap': 15, 'cafe_expensive': 20,
            'car_fuel': 15, 'car_service': 10, 'car_rent': 0,
            'shopping_online': 20, 'shopping_luxury': 0, 'shopping_tech': 0,
            'delivery': 20, 'household': 20, 'study_job': 0,
            'medical_cure': 20, 'medical_beauty': 10, 'living': 15,
            'culture': 15, 'hobby_active': 15, 'hobby_creative': 5,
            'travel_domestic': 5, 'travel_overseas': 0, 'baby_living': 35,
        },
        'amt_range': {
            'transport_public': (1400, 2800), 'transport_taxi': (5000, 15000),
            'food_cheap': (4500, 6000), 'food_middle': (8000, 16000), 'food_expensive': (30000, 50000),
            'food_luxury': (100000, 300000),
            'cafe_cheap': (1500, 4500), 'cafe_expensive': (5000, 30000),
            'car_fuel': (50000, 150000), 'car_service': (150000, 250000), 'car_rent': (50000, 100000),
            'shopping_online': (50000, 500000), 'shopping_luxury': (250000, 1000000), 'shopping_tech': (100000, 500000),
            'delivery': (20000, 50000), 'household': (15000, 50000), 'study_job': (5000, 150000),
            'medical_cure': (10000, 50000), 'medical_beauty': (50000, 150000), 'living': (50000, 150000),
            'culture': (10000, 50000), 'hobby_active': (30000, 150000), 'hobby_creative': (50000, 150000),
            'travel_domestic': (100000, 300000), 'travel_overseas': (500000, 1500000), 'baby_living': (30000, 100000),
        }
    },


    '프리랜서': {
        'asset_range': (10000000, 50000000), 'income_amount': (1500000, 7000000), 'pay_day_type': 'random',
        'financial_config': {'finance_savings': {'count': (1, 1), 'amt': (500000, 1000000)},
                             'finance_invest': {'count': (0, 2), 'amt': (100000, 500000)}},
        'subs_config': {'work': {'pool': ['Adobe_Creative_Cloud', 'ChatGPT_Plus', 'GitHub_Copilot'], 'count': (2, 4)}},
        'event_config': {'tech_prob': 0.9, 'tech_budget': (2000000, 4000000), 'travel_count': (0, 1)},

        'weights': {
            'transport_public': 10, 'transport_taxi': 10,
            'food_cheap': 10, 'food_middle': 20, 'food_expensive': 10, 'food_luxury': 5,
            'cafe_cheap': 15, 'cafe_expensive': 30,
            'car_fuel': 15, 'car_service': 10, 'car_rent': 0,
            'shopping_online': 15, 'shopping_luxury': 5, 'shopping_tech': 10,
            'delivery': 20, 'household': 20, 'study_job': 0,
            'medical_cure': 10, 'medical_beauty': 10, 'living': 15,
            'culture': 15, 'hobby_active': 15, 'hobby_creative': 5,
            'travel_domestic': 10, 'travel_overseas': 0, 'baby_living': 5,
        },
        'amt_range': {
            'transport_public': (1400, 2800), 'transport_taxi': (5000, 30000),
            'food_cheap': (4500, 6000), 'food_middle': (8000, 16000), 'food_expensive': (30000, 50000),
            'food_luxury': (100000, 300000),
            'cafe_cheap': (1500, 4500), 'cafe_expensive': (5000, 30000),
            'car_fuel': (50000, 150000), 'car_service': (150000, 250000), 'car_rent': (50000, 100000),
            'shopping_online': (50000, 500000), 'shopping_luxury': (250000, 1000000), 'shopping_tech': (100000, 500000),
            'delivery': (20000, 50000), 'household': (15000, 50000), 'study_job': (5000, 150000),
            'medical_cure': (10000, 50000), 'medical_beauty': (50000, 150000), 'living': (50000, 150000),
            'culture': (10000, 50000), 'hobby_active': (30000, 150000), 'hobby_creative': (50000, 150000),
            'travel_domestic': (100000, 300000), 'travel_overseas': (500000, 1500000), 'baby_living': (30000, 100000),
        }
    },
    '평균': {
        # 자산: 많지도 적지도 않음 (비상금 정도)
        'asset_range': (5000000, 20000000),
        # 소득: 중소기업/계약직 수준 (200~280만원)
        'income_amount': (2000000, 2800000),
        'pay_day': 10, 'pay_day_type': 'fixed',  # 중소기업 월급날 국룰 10일/25일

        # 금융: 최소한의 방어
        'financial_config': {
            'finance_savings': {'count': (1, 1), 'amt': (50000, 100000)},
            'finance_insurance': {'count': (0, 1), 'amt': (30000, 50000)},  # 실비 정도만
            'finance_invest': {'count': (0, 2), 'amt': (50000, 300000)}
        },

        # 구독: 남들 다 보는거 하나 (유튜브 or 넷플)
        'subs_config': {
            'media': {'pool': ['유튜브프리미엄', '넷플릭스'], 'count': (1, 1)},
            'life': {'pool': ['쿠팡와우멤버십'], 'count': (0, 1)},
            'work': {'pool': [], 'count': (0, 0)}
        },

        # 이벤트: 큰 욕심 없음. 폰 고장나면 저렴한걸로 바꿈. 여행은 가끔 국내.
        'event_config': {
            'tech_prob': 0.1, 'tech_budget': (500000, 1000000),  # 보급형 기기 구매
            'travel_count': (0, 1), 'travel_type': 'domestic', 'travel_budget': (150000, 300000)  # 가성비 여행
        },

        'weights': {
            'transport_public': 15, 'transport_taxi': 10,
            'food_cheap': 10, 'food_middle': 20, 'food_expensive': 10, 'food_luxury': 5,
            'cafe_cheap': 15, 'cafe_expensive': 10,
            'car_fuel': 15, 'car_service': 10, 'car_rent': 0,
            'shopping_online': 15, 'shopping_luxury': 5, 'shopping_tech': 10,
            'delivery': 20, 'household': 20, 'study_job': 0,
            'medical_cure': 10, 'medical_beauty': 10, 'living': 15,
            'culture': 15, 'hobby_active': 15, 'hobby_creative': 5,
            'travel_domestic': 5, 'travel_overseas': 0, 'baby_living': 0,
        },
        'amt_range': {
            'transport_public': (1400, 2800), 'transport_taxi': (5000, 30000),
            'food_cheap': (4500, 6000), 'food_middle': (8000, 16000), 'food_expensive': (30000, 50000),
            'food_luxury': (100000, 300000),
            'cafe_cheap': (1500, 4500), 'cafe_expensive': (5000, 30000),
            'car_fuel': (50000, 150000), 'car_service': (150000, 250000), 'car_rent': (50000, 100000),
            'shopping_online': (50000, 500000), 'shopping_luxury': (250000, 1000000), 'shopping_tech': (100000, 500000),
            'delivery': (20000, 50000), 'household': (15000, 50000), 'study_job': (5000, 150000),
            'medical_cure': (10000, 50000), 'medical_beauty': (50000, 150000), 'living': (50000, 150000),
            'culture': (10000, 50000), 'hobby_active': (30000, 150000), 'hobby_creative': (50000, 150000),
            'travel_domestic': (100000, 300000), 'travel_overseas': (500000, 1500000), 'baby_living': (30000, 100000),
        }
    }
}

SAVING_PRODUCTS_WEIGHTS = {
    "적금": 0.5,
    "정기예금": 0.3,
    "주택청약": 0.2
}


ACCOUNT_CATEGORIES = {
    "입출금": {
        "banks": ["국민은행", "신한은행", "우리은행", "하나은행", "카카오뱅크", "토스뱅크", "IBK기업은행", "농협은행"],
        "balance_range": (0, 20_000_000),
        "count": (1, 2)   # 보통 1~2개
    },
    "예적금": {
        "banks": ["국민은행", "신한은행", "우리은행", "하나은행", "새마을금고", "신협", "카카오뱅크", "농협은행"],
        "products": SAVING_PRODUCTS_WEIGHTS,
        "balance_range": (1_000_000, 50_000_000),
        "count": (0, 2)
    },
    "증권": {
        "banks": ["미래에셋", "삼성증권", "키움증권", "NH투자증권", "토스증권"],
        "balance_range": (0, 100_000_000),
        "count": (0, 2)
    },
    "대출": {
        "banks": ["국민은행", "신한은행", "카카오뱅크", "우리은행", "농협은행", "하나은행"],
        "balance_range": (5_000_000, 200_000_000),  
        "count": (0, 2)
    }
}

# 시간 및 날짜 생성
def get_realistic_time(category, is_weekend=False):
    """카테고리와 요일에 따라 현실적인 결제 시간을 반환"""
    hour = random.randint(10, 22)  # 기본값

    # [1] 금융/구독: 주로 오전 시간대 자동이체
    if 'finance' in category or 'subscription' in category:
        hour = random.randint(8, 11)

    # [2] 식사: 가격대별 피크타임 차별화
    elif category == 'food_cheap':  # 아침/점심/간식
        hour = random.choices([8, 12, 18, 21], weights=[20, 40, 30, 10])[0]
    elif category == 'food_middle':  # 점심/저녁 식사
        hour = random.choices([12, 18], weights=[60, 40])[0]
    elif category == 'food_expensive':  # 저녁 약속/회식
        hour = random.randint(18, 21)
    elif category == 'food_luxury':  # 파인다이닝 예약 (저녁)
        hour = random.randint(18, 19)

    # [3] 교통: 출퇴근 vs 주말
    elif category == 'transport_public':
        if not is_weekend:  # 평일 출퇴근
            hour = random.randint(7, 9) if random.random() < 0.5 else random.randint(18, 20)
        else:  # 주말 나들이
            hour = random.randint(11, 20)

    # [4] 택시: 심야 할증 시간대 or 급한 이동
    elif category == 'transport_taxi':
        hour = random.randint(22, 23) if random.random() < 0.3 else random.randint(8, 19)

    # [5] 취미: 주말 낮 or 평일 저녁
    elif 'hobby' in category:
        hour = random.randint(10, 16) if is_weekend else random.randint(19, 21)

    return hour


def get_event_date(year, season='random'):
    """이벤트(여행, 기기구매)가 발생할 날짜를 랜덤 생성"""
    if season == 'summer':
        month = random.choice([7, 8])
    elif season == 'winter':
        month = random.choice([1, 2, 12])
    else:
        month = random.randint(1, 12)

    # 1~28일 사이로 안전하게 생성 (2월 등 고려)
    day = random.randint(1, 28)
    return datetime(year, month, day)


# 메인 함수
def generate_merged_user_data(user_id):
    config = PERSONAS[random.choice(list(PERSONAS.keys()))]
    transaction_list = []

    my_income = random.randint(*config['income_amount'])
    my_spending_bias = random.randint(-1, 1)

    # [1] 기초 자산 및 [2] 고정 지출/이벤트 설정은 기존과 동일 (생략하지 않고 전체 흐름 유지)
    # -------------------------------------------------------------------------
    current_balance = random.randint(*config['asset_range'])
    transaction_list.append({
        'user_id': user_id, 'trans_dtime': START_DATE, 'trans_type': '입금',
        'category': '기초자산', 'merchant_name': '전월이월',
        'amount': current_balance, 'method': '-', 'balance': current_balance
    })

    my_fixed_costs = []
    # (구독 설정)
    if 'subs_config' in config:
        for cat, setting in config['subs_config'].items():
            pool = setting['pool']
            if not pool: continue
            count = random.randint(*setting['count'])
            selected = random.sample(pool, k=min(count, len(pool)))
            for name in selected:
                price = SUBSCRIPTION_PRICES.get(name, 9900)
                my_fixed_costs.append(
                    {'cat': f'subscription_{cat}', 'name': name, 'amt': price, 'day': random.randint(1, 28)})
    # (금융 설정)
    if 'financial_config' in config:
        for cat, setting in config['financial_config'].items():
            count = random.randint(*setting['count'])
            if count > 0:
                merchs = MERCHANTS_DB[cat]
                selected = random.sample(merchs, k=min(count, len(merchs)))
                for m in selected:
                    amt = random.randint(*setting['amt']) // 1000 * 1000
                    pay_day = config.get('pay_day', 1)
                    my_fixed_costs.append(
                        {'cat': cat, 'name': m, 'amt': amt, 'day': pay_day + 1 if pay_day < 28 else 1})

    # (이벤트 설정)
    my_events = []
    evt_conf = config.get('event_config', {})
    if random.random() < evt_conf.get('tech_prob', 0):
        budget = random.randint(*evt_conf['tech_budget'])
        my_events.append({'date': get_event_date(START_DATE.year), 'cat': 'shopping_tech',
                          'merch': random.choice(MERCHANTS_DB['shopping_tech']), 'amt': budget})
    travel_cnt = random.randint(*evt_conf.get('travel_count', (0, 0)))
    for _ in range(travel_cnt):
        t_type = evt_conf.get('travel_type', 'domestic')
        budget = random.randint(*evt_conf.get('travel_budget', (0, 0)))
        my_events.append({'date': get_event_date(START_DATE.year, 'random'), 'cat': f'travel_{t_type}',
                          'merch': random.choice(MERCHANTS_DB[f'travel_{t_type}']), 'amt': budget})
    # -------------------------------------------------------------------------

    current_date = START_DATE
    while current_date <= END_DATE:
        # [A] 수입 처리
        is_payday = False
        if config.get('pay_day_type') == 'fixed':
            if current_date.day == config.get('pay_day', 1): is_payday = True
        elif config.get('pay_day_type') == 'random':
            if random.random() < 0.05: is_payday = True

        if is_payday:
            this_income = random.randint(*config['income_amount']) if 'random' in str(
                config.get('pay_day_type')) else my_income
            current_balance += this_income
            transaction_list.append({
                'user_id': user_id, 'trans_dtime': current_date.replace(hour=9, minute=0),
                'trans_type': '입금', 'category': '수입', 'merchant_name': '급여/입금',
                'amount': this_income, 'balance': current_balance, 'method': '계좌이체'
            })

        # [B] 고정 지출
        for cost in my_fixed_costs:
            if current_date.day == cost['day']:
                if current_balance >= cost['amt']:
                    current_balance -= cost['amt']
                    transaction_list.append({
                        'user_id': user_id, 'trans_dtime': current_date.replace(hour=10, minute=0),
                        'trans_type': '출금', 'category': cost['cat'], 'merchant_name': cost['name'],
                        'amount': cost['amt'], 'balance': current_balance, 'method': '자동이체'
                    })

        # [C] 이벤트
        for evt in my_events:
            if current_date.date() == evt['date'].date():
                if current_balance >= evt['amt']:
                    current_balance -= evt['amt']
                    transaction_list.append({
                        'user_id': user_id, 'trans_dtime': current_date.replace(hour=14, minute=0),
                        'trans_type': '출금', 'category': evt['cat'], 'merchant_name': evt['merch'],
                        'amount': evt['amt'], 'balance': current_balance, 'method': '카드(일시불)'
                    })

        # ==============================================================================
        # [D] 변동 지출 (중복 시간 방지 로직 적용)
        # ==============================================================================
        base_count = max(0, 3 + my_spending_bias)
        if current_date.weekday() >= 5: base_count += 1
        today_tx_cnt = random.randint(0, base_count + 2)

        # [Day Log] 오늘 몇 시에 밥을 먹었는지 기록하는 리스트
        # 형식: [12, 18] -> 12시와 18시에 밥 먹음
        today_food_hours = []

        for _ in range(today_tx_cnt):
            weights = config.get('weights', {})
            if not weights: continue

            valid_cats = [k for k, v in weights.items() if v > 0]
            if not valid_cats: continue

            category = random.choices(list(weights.keys()), weights=list(weights.values()))[0]
            if not MERCHANTS_DB.get(category): continue

            merchant = random.choice(MERCHANTS_DB[category])

            # 1. 시간 생성
            hour = get_realistic_time(category, (current_date.weekday() >= 5))

            # 2. [New] 식사 시간 충돌 체크 로직
            if 'food' in category:
                # 이미 오늘 2끼 이상 먹었으면 식사 스킵 (과식 방지)
                if len(today_food_hours) >= 2:
                    continue

                    # 기존 식사 시간과 3시간 이내면 시간 조정 시도
                conflict = False
                for eaten_hour in today_food_hours:
                    if abs(hour - eaten_hour) < 4:  # 최소 4시간 간격 필요
                        conflict = True
                        break

                if conflict:
                    # 충돌 나면 시간을 강제로 변경 시도 (점심<->저녁)
                    # 만약 지금 뽑힌게 점심(11~14)인데 이미 먹었다면 -> 저녁(17~20)으로 변경
                    if 11 <= hour <= 14:
                        hour = random.randint(18, 20)
                    elif 17 <= hour <= 21:
                        hour = random.randint(11, 13)

                    # 변경 후에도 또 충돌나면(이미 점심,저녁 다 먹음) -> 스킵
                    for eaten_hour in today_food_hours:
                        if abs(hour - eaten_hour) < 4:
                            conflict = True
                            break
                    if conflict: continue  # 이번 지출은 포기

                # 통과했으면 식사 시간 기록
                today_food_hours.append(hour)

            # 3. 금액 결정 및 결제
            amt_range = config.get('amt_range', {}).get(category, (5000, 20000))
            amount = random.randint(*amt_range)
            amount = (amount // 100) * 100

            if current_balance >= amount:
                current_balance -= amount
                transaction_list.append({
                    'user_id': user_id, 'trans_dtime': current_date.replace(hour=hour, minute=random.randint(0, 59)),
                    'trans_type': '출금', 'category': category, 'merchant_name': merchant,
                    'amount': amount, 'balance': current_balance, 'method': '카드'
                })

        current_date += timedelta(days=1)

    return pd.DataFrame(transaction_list).sort_values('trans_dtime').reset_index(drop=True)

def save_spending_df_to_db(df, user):
    # 1. 데이터프레임의 시간을 'Asia/Seoul' 시간대로 일괄 변환
    # 만약 데이터가 이미 datetime 타입이 아니라면 변환부터 수행
    df["trans_dtime"] = pd.to_datetime(df["trans_dtime"])

    # 시간대 정보가 없는 경우에만 한국 시간(Asia/Seoul)을 입혀줌
    if df["trans_dtime"].dt.tz is None:
        df["trans_dtime"] = df["trans_dtime"].dt.tz_localize('Asia/Seoul')
    else:
        # 이미 다른 시간대가 있다면 한국 시간으로 변환
        df["trans_dtime"] = df["trans_dtime"].dt.tz_convert('Asia/Seoul')

    records = []

    for _, row in df.iterrows():
        spend = Spending(
            user=user,
            spend_date=row['trans_dtime'],   # DateField
            method=row['method'],
            price=row['amount'],
            details=row['merchant_name'],           # merchant_name → details
            transaction_type=row['trans_type'],
            memo=""                                  # memo 없음 → 빈값
        )
        records.append(spend)

    Spending.objects.bulk_create(records)
    

def get_asset_details_by_month(moni_user, target_month=None):
    """
    특정 월의 저축/투자 상세 내역(가맹점명, 금액)을 확인합니다.
    """
    df = spending_to_dataframe(moni_user)
    df["trans_dtime"] = pd.to_datetime(df["trans_dtime"]).dt.tz_convert('Asia/Seoul')
    df["year_month"] = df["trans_dtime"].dt.strftime("%Y-%m")
    
    # 저축/투자 내역만 필터링
    assets_df = df[df['category'].isin(['savemoney', 'investment'])]
    
    if target_month:
        assets_df = assets_df[assets_df['year_month'] == target_month]
        
    return assets_df[['trans_dtime', 'category', 'merchant_name', 'amount']].sort_values('trans_dtime')

def sync_bank_accounts_from_report(moni_user):
    """
    get_monthly_asset_report의 최종 계산 결과를 가져와서 
    실제 BankAccount DB의 잔액을 최신화합니다.
    """
    # 1. 월별 리포트 가져오기 (가장 최신 계산 결과 포함)
    report_df = _helpers.get_monthly_asset_report(moni_user)
    if isinstance(report_df, str): return # 데이터 없음

    # 가장 마지막 월(현재 달)의 데이터 추출
    latest_stat = report_df.iloc[-1]
    
    # 2. 입출금 계좌 업데이트 (리포트의 '통장잔고' 반영)
    # 사용자가 입출금 계좌 객체도 DB에 남기길 원할 경우 실행
    main_acc, _ = BankAccount.objects.update_or_create(
        user=moni_user,
        category="입출금",
        bank="메인은행", # 대표 명칭
        defaults={'balance': latest_stat['통장잔고']}
    )

    # 3. 저축/투자 계좌 세부 업데이트
    # 리포트에서는 합계만 나오므로, 가맹점별 세부 잔액은 Spending에서 다시 가져오되
    # 리포트와 동일한 로직(전체 합산)으로 적용합니다.
    df = spending_to_dataframe(moni_user)

    # 1. 범위 설정 (최솟값, 최댓값)
    min_savings = 1000000
    max_savings = 10000000

    # 2. 범위 내 정수 랜덤 출력
    random_savings = random.randint(min_savings, max_savings)
    
    # [저축 계좌들]
    savings_detail = df[df['category'] == 'savemoney'].groupby('merchant_name')['amount'].sum()
    for bank_name, total_price in savings_detail.items():
        BankAccount.objects.update_or_create(
            user=moni_user,
            category="예적금",
            bank=bank_name,
            defaults={'balance': total_price + random_savings}
        )

    # 1. 범위 설정 (최솟값, 최댓값)
    min_invest = 500000 
    max_invest = 5000000

    # 2. 범위 내 정수 랜덤 출력
    random_invest = random.randint(min_invest, max_invest)

    # [투자 계좌들]
    invest_detail = df[df['category'] == 'investment'].groupby('merchant_name')['amount'].sum()
    for invest_name, total_price in invest_detail.items():
        BankAccount.objects.update_or_create(
            user=moni_user,
            category="증권",
            bank=invest_name,
            defaults={'balance': total_price + random_invest}
        )

    # print(f"✅ {moni_user.name}님의 계좌 잔액이 리포트 기준으로 동기화되었습니다.")



# category
DICT_FILE = "merchant_dict.json" 
def use_gemini_api():

    try:
        GOOGLE_API_KEY = 'AIzaSyCzmRRnisqbIeZn12VlwFEOsI8sj-RJv0A'
        genai.configure(api_key=GOOGLE_API_KEY)
    except Exception as e:
        print("❌ API 키 오류: 왼쪽 '보안 비밀' 설정을 확인하세요.")
        raise e

    model = genai.GenerativeModel(
        "models/gemini-2.5-flash",
        generation_config={"response_mime_type": "application/json"}
    )
    return model

model = use_gemini_api()

def load_dictionary():
    if os.path.exists(DICT_FILE): 
        with open(DICT_FILE, "r", encoding="utf-8") as f: 
            return json.load(f) 
        return {} 

def save_dictionary(data):
    with open(DICT_FILE, "w", encoding="utf-8") as f: 
        json.dump(data, f, ensure_ascii=False, indent=4)


def auto_categorize_spending_with_gemini(moni_user):

    qs = Spending.objects.filter(
    user=moni_user).filter(
    Q(category__isnull=True) | Q(category='')).values('spending_id', 'details')

    total_rows = qs.count()
    # print(f"\nGemini 자동 분류 시작 | 대상 {total_rows}건")

    if total_rows == 0:
        print("분류할 데이터 없음")
        return
    
    if not qs.exists():
        return

    df = pd.DataFrame(list(qs))

    # details 전처리
    df['details'] = df['details'].astype(str).str.strip()
    df = df[df['details'] != '']

    if df.empty:
        return

    # 🔥 Gemini로 category 분류
    df = ask_jemini_category_from_spending(df)

    # 🔥 DB 업데이트 (bulk_update 사용)
    spendings_to_update = []
    for _, row in df.iterrows():
        spendings_to_update.append(
            Spending(spending_id=row['spending_id'], category=row['category'])
        )

    if spendings_to_update:
        Spending.objects.bulk_update(spendings_to_update, ['category'])
        # print(f"⏳ DB 업데이트 완료: {len(spendings_to_update)}건")
        
def get_categories_batch(details_list):
    input_text_data = json.dumps(details_list, ensure_ascii=False)

    prompt = f"""
        너는 금융 소비 패턴을 분류하는 카테고리 분류기이다.

        다음 중 하나의 카테고리를 반드시 선택해라:
        ['food','coffee','shopping','transport','entertainment',
        'beauty','health','investment','savemoney','income','living','etc']

        [입력 데이터]
        {input_text_data}

        [출력 형식]
        JSON 배열만 반환:
        [
        {{"merchant": "입력 텍스트", "category": "coffee"}}
        ]
        """

    retry = 0
    while True:
        try:
            response = model.generate_content(
                prompt,
                request_options={'timeout': 30}
            )

            text = response.text.strip()
            if text.startswith("```"):
                text = text.replace("```json", "").replace("```", "").strip()

            return json.loads(text)

        except Exception:
            retry += 1
            if retry >= 5:
                return []
            time.sleep(2)

       
def ask_jemini_category_from_spending(df):
    global_dict = load_dictionary()

    current_details = df['details'].unique().tolist()
    unknown_details = [d for d in current_details if d not in global_dict]

    # print(
    #     f"📊 전체 {len(current_details)}개 | "
    #     f"기존 {len(current_details) - len(unknown_details)} | "
    #     f"신규 {len(unknown_details)}"
    # )

    if unknown_details:
        BATCH_SIZE = 30
        new_findings = {}

        for i in range(0, len(unknown_details), BATCH_SIZE):
            batch = unknown_details[i:i + BATCH_SIZE]

            batch_result = get_categories_batch(batch)

            for item in batch_result:
                detail = item.get("merchant")   # Gemini 출력 키
                cat = item.get("category", "etc")

                if isinstance(cat, str):
                    cat = cat.strip().lower()

                if detail:
                    new_findings[detail] = cat

        global_dict.update(new_findings)
        save_dictionary(global_dict)

    df['category'] = df['details'].map(global_dict)
    df['category'] = df['category'].fillna('etc')

    return df


def spending_to_dataframe(moni_user):
    qs = Spending.objects.filter(user=moni_user).values(
        "spend_date",
        "price",
        "transaction_type",
        "category",
        "details",
    )

    df = pd.DataFrame(list(qs))

    if df.empty:
        return df

    # extract_feature_vector에서 쓰는 컬럼명으로 맞추기
    df = df.rename(columns={
        "spend_date": "trans_dtime",
        "price": "amount",
        "transaction_type": "trans_type",
        "category": "category",
        "details": "merchant_name",
    })

    return df

def extract_feature_vector(moni_user):
    
    df = spending_to_dataframe(moni_user)
    # print("df : ", df.head(10))
    
    df["trans_dtime"] = pd.to_datetime(df["trans_dtime"])
    df["year_month"] = df["trans_dtime"].dt.strftime("%Y-%m")

    income_df = df[df["trans_type"] == "입금"]
    expense_df = df[df["trans_type"] == "출금"]

    income_month = income_df.groupby("year_month")["amount"].sum().reset_index(name="income")
    expense_month = expense_df.groupby("year_month")["amount"].sum().reset_index(name="expense")

    summary = income_month.merge(expense_month, how="outer", on="year_month").fillna(0)
    summary["remain"] = summary["income"] - summary["expense"]

    saving_month = df[df["category"] == "savemoney"].groupby("year_month")["amount"].sum().reset_index(name="saving_amount")
    summary = summary.merge(saving_month, how="left", on="year_month").fillna(0)

    invest_month = df[df["category"] == "investment"].groupby("year_month")["amount"].sum().reset_index(name="invest_amount")
    summary = summary.merge(invest_month, how="left", on="year_month").fillna(0)

    fixed_month = df[df["category"].isin(["living", "transport"])].groupby("year_month")["amount"].sum().reset_index(name="fixed_amount")
    month_df = summary.merge(fixed_month, how="left", on="year_month").fillna(0)
    
    feature = {}
    
    # 1) saving_rate 
    total_saving = month_df["saving_amount"].sum()
    total_expense = month_df["expense"].sum()
    feature["saving_rate"] = total_saving / total_expense if total_expense > 0 else 0

    # 2) remain_ratio = (월말 잔액 평균) / 평균 소득
    avg_income = month_df["income"].mean()
    avg_remain = month_df["remain"].mean()
    feature["remain_ratio"] = avg_remain / avg_income if avg_income > 0 else 0

    # 4) invest_ratio = 총 투자 지출 / 총 지출
    total_invest = month_df["invest_amount"].sum()
    feature["invest_ratio"] = total_invest / total_expense if total_expense > 0 else 0

    # 5) spend_volatility = 지출 변동성(표준편차/평균)
    exp_std = month_df["expense"].std()
    exp_mean = month_df["expense"].mean()
    feature["spend_volatility"] = exp_std / exp_mean if exp_mean > 0 else 0

    # 6) peak_spend_months = 특정 월에서 지출이 평균의 1.5배 이상 폭발한 횟수
    feature["peak_spend_months"] = int((month_df["expense"] > exp_mean * 1.5).sum())

    total_fixed = month_df["fixed_amount"].sum()
    feature["fixed_cost_ratio"] = total_fixed / total_expense if total_expense > 0 else 0
    
    # print("feature vector : ", feature)
    return feature

FEATURE_ORDER = [
    "saving_rate",
    "remain_ratio",
    "invest_ratio",
    "spend_volatility",
    "peak_spend_months",
    "fixed_cost_ratio"
    
]

def use_classify_model(feature):
    
    feature_vector = pd.DataFrame([{k: float(feature[k]) for k in FEATURE_ORDER}])
    loaded = joblib.load("model.joblib")
    loaded_model = loaded["RandomForestmodel"]
    encoder = loaded["Label_Encoder"]
    scaler = loaded["RobustScaler"]
    
    x_test_scaled = scaler.transform(feature_vector)
    x_test = pd.DataFrame(x_test_scaled, columns=FEATURE_ORDER)
    y_pred = loaded_model.predict(x_test)
    y_pred = encoder.inverse_transform(y_pred)
    
    # feature_data['user_type'] = y_pred[0]

    return y_pred[0]