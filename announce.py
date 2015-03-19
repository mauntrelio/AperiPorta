#!/usr/bin/python
# -*- coding: utf-8 -*-
from apriporta import play_message

import os
import sqlite3
import time
import calendar
import json 

basedir = os.path.dirname(os.path.abspath(__file__))

def time2sql(time,config):
  return int(round( (time - config["TIMESTAMP_OFFSET"]) * config["TIMESTAMP_MULTIPLIER"] ))

def get_winner(time_start, time_end=0, db):
  if time_end ==0:
    time_end = time.time()
  conn = sqlite3.connect(db)
  cur = conn.cursor()
  sql = "SELECT sum(points), user FROM openings WHERE datetime >= ? AND datetime < ? \
  GROUP BY user ORDER BY sum(points) DESC LIMIT 1"
  params = (time2sql(time_start,config),time2sql(time_end,config))
  cur.execute(sql, params)
  res = cur.fetchall()
  winner = res[0][1] 
  conn.close()
  return winner  


if __name__ == '__main__':

  config = json.load(open(basedir + '/config.json','r'))

  cachedir = basedir + '/static/audio/cache/'
  db = basedir + '/db/apriporta.db'

  adesso = time.localtime()
  anno, mese, gsett, gmese, ora, minuto, secondo = adesso[0], adesso[1], adesso[6], adesso[2], adesso[3], adesso[4], adesso[5]
  ultimodelmese = calendar.monthrange(anno, mese)[1]

  # suonare musica (rullo di tamburi più ta-daa)

  # venerdì: vincitore della settimana
  # if gsett == 4:
  if gsett > -1:
    time_start = time.time() - gsett*86400 - 3600*ora - 60*minuto - secondo
    # annunciare vincitore della settimana
    print u"Il vincitore dell'apriporta della settimana è..., %s!!" % get_winner(time_start,0,db)

  time.sleep(5)

  # vincitore del mese
  # TODO: valutare le festività
  # if gmese == ultimodelmese:
  if gmese > -1:    
    time_start = time.time() - (gmese - 1)*86400 - 3600*ora - 60*minuto - secondo
    # annunciare vincitore del mese
    print u"Il vincitore dell'apriporta del mese è..., %s!!" % get_winner(time_start,0,db)

  time.sleep(5)

  # suonare applausi
