#!/usr/bin/python
# -*- coding: utf-8 -*-
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn
from Queue import Queue
from jinja2 import Environment, FileSystemLoader
from datetime import datetime 
from email.utils import parsedate
from calendar import timegm
from hashlib import md5

import RPi.GPIO as GPIO
import Cookie
import sqlite3
import time
import threading
import cgi
import os
import re
import locale
import json
import mimetypes
import shutil

locale.setlocale(locale.LC_TIME, "it_IT.UTF8")
basedir = os.path.dirname(os.path.abspath(__file__))
template_path = basedir + '/templates/'
GLOCK = threading.Lock()

LOG_FILE_WIN = basedir + '/log/apriporta.log'
LOG_FILE = basedir + '/log/debug.log'

LAST_OPEN = 0
LAST_OPENER = ''
OPENERS = []

class configClass:
    """Trasforma un dizionario in un oggetto"""
    def __init__(self, **entries):
        self.__dict__.update(entries)

class ApriPorta(BaseHTTPRequestHandler):

    server_version = "ApeRiPorta/1.0.8"

    # mimetypes per file statici
    if not mimetypes.inited:
        mimetypes.init() # legge i mime.types di sistema
    extensions_map = mimetypes.types_map.copy()    

    def log_message(self, format, *args):

        # log generico
        open(LOG_FILE, "a").write("%s - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(),format%args))

        # log delle aperture
        if self.url.path == '/open' and self.user:
            if self.winner == 1:
                locale.setlocale(locale.LC_TIME, "it_IT.UTF8")
                timestamp = datetime.fromtimestamp(self.now).strftime("%H:%M:%S.%f\t%A %d %B %Y")
                strformat = "\n<b>%s %s\t(%s)</b>\n"
                open(LOG_FILE_WIN, "a").write(strformat % (self.user.strip().ljust(15).encode('utf-8'), timestamp, self.client_address[0]) )
            else:
                delay = self.now - LAST_OPEN
                strformat = "%s %0.3f\t(%s)\n"
                open(LOG_FILE_WIN, "a").write(strformat % (self.user.strip().ljust(15).encode('utf-8'), delay, self.client_address[0]) )


    def do_GET(self):
        """Gestione richieste GET"""
        self.now = time.time() # calcolo subito l'istante della chiamata
        self.winner = 0
        self.user = None
        self.check_user() # controllo login

        self.template_vars = {'user': self.user, 'config': config, 'ip': self.client_address[0]}  
        self.url = cgi.urlparse.urlparse(self.path)
        # routing

        if self.url.path == '/':        # home page
            self.home()
        elif self.url.path == '/open':  # apertura
            if not self.user:
                self.sign()
            else:
                self.open()
        elif self.url.path == '/log':   # log
            self.log()
        elif self.url.path == '/sign':   # registrazione
            self.sign()
        elif self.url.path == '/rank':   # classifica
            self.rank()
        elif self.url.path == '/say':    # sintesi vocale
            self.say()
        elif self.url.path == '/hour':   # segnale orario
            self.hour()
        elif self.url.path[:7] == '/static': # static files
            self.serve_static()
            return            
        else:
            self.send_error(404)
            return
        
        self.send_answer()
        return
    
    def do_POST(self):
        """Gestione richieste POST"""
        self.url = cgi.urlparse.urlparse(self.path)
        self.user = None
        self.check_user() # controllo login        
        self.form = cgi.FieldStorage(
        fp=self.rfile, 
        headers=self.headers,
        environ={'REQUEST_METHOD':'POST',
                 'CONTENT_TYPE':self.headers['Content-Type'],
                 })  
        if self.url.path == '/sign':   # registration
            self.sign()
        elif self.url.path == '/say':   # sintesi vocale
            self.say()
        else:
            self.send_error(404)
            return

        self.send_answer()
        return

    def check_user(self):
        """Controllo utente, da cookie: username"""
        #"""Controllo utente, da cookie o mapping ip: username"""
        # primo controllo: cookie
        if 'cookie' in self.headers:
            cookie = Cookie.SimpleCookie()
            cookie.load(self.headers['cookie'])
            if 'user' in cookie:
                if cookie['user'].value:
                    self.user = cgi.urllib.unquote(cookie['user'].value)

        # secondo controllo, ricerca in USERS        
        #if not self.user:
        #    if self.client_address[0] in USERS:
        #        self.user = USERS[self.client_address[0]]

    def send_answer(self):
        """Gestione generica invio contenuti HTTP"""
        self.send_response(200)
        self.send_header("Content-Type", self.content_type)
        self.send_header("Content-Length", str(len(self.content)))
        # imposta cookie user
        if self.user:
            locale.setlocale(locale.LC_TIME, "C")
            cookie_expires = time.strftime("%a, %d-%b-%Y %T GMT", time.gmtime(time.time()+config.COOKIE_EXPIRES))
            cookie_value = 'user=%s; Expires=%s; Path=/' % (cgi.urllib.quote(self.user), cookie_expires)
            self.send_header("Set-Cookie", cookie_value)
        self.end_headers()
        self.wfile.write(self.content)

    def home(self):
        """Home Page"""
        self.content_type = 'text/html'
        self.content = self.render_template('home.html')

    def log(self):
        """Visualizzazione log"""
        log_content = self.tail()
        self.content_type = 'text/html'
        if 'x-requested-with' in self.headers:
            # richiesta via Ajax
            self.content = log_content.encode('utf-8')
        else:
            # richiesta via finestra normale
            self.template_vars.update(dict(log=log_content))
            self.content = self.render_template('log.html')

    def say(self):
        """Sintesi vocale"""
        if self.command == 'GET':
            self.content_type = 'text/html'
            self.content = self.render_template('say.html')
        elif self.command == 'POST':
            self.content_type = 'application/json'
            self.content = json.dumps(dict(ok=1))
            if 'message' in self.form.keys():
                play_message(self.form['message'].value.decode('utf-8'), basedir + '/static/audio/cache/')

    def hour(self):
        """Segnale orario"""
        (ore, minuti) = time.strftime("%H %M").split(" ")
        if minuti != "00":
            segnale = "Sono le ore %s e %s minuti!" % (ore, minuti)
        else:
            segnale = "Sono le ore %s in punto!" % ore
            
        play_message(segnale, basedir + '/static/audio/cache/')
        self.content_type = 'application/json'
        self.content = json.dumps(dict(hour=ore,minute=minuti))

    def sign(self):
        """Registrazione utente"""
        if self.command == 'GET':
            if 'x-requested-with' in self.headers:
                # richiesta via Ajax
                self.content_type = 'application/json'
                self.content = json.dumps(dict(winner=-1))
            else:
                self.content_type = 'text/html'
                self.template_vars.update({'ip':self.client_address[0]})
                if self.user:
                    self.template_vars.update({'username':self.user})
                self.content = self.render_template('register.html')
        
        elif self.command == 'POST':
            
            #global USERS
            response = {}
            error = ''

            if 'username' in self.form.keys():
                username = self.form['username'].value.decode('utf-8')[0:15]
                if not username:
                    error = 'Inserire un nome utente valido' 
            else:
                error = 'Inserire il nome utente'

            if error:
                response['status'] = 'ERROR'
                response['message'] = error
            else:
                #USERS.update({self.client_address[0]:username})
                #with open(basedir + '/users.json', 'w') as outfile:
                #    json.dump(USERS, outfile, sort_keys=True, indent=4)
                
                if 'updatedbuser' in self.form.keys():
                    if self.form['updatedbuser'].value == 'on':
                        DbCmd("UPDATE openings SET user = ? WHERE user = ?", (username, self.user) )

                if 'updatedbip' in self.form.keys():
                    if self.form['updatedbip'].value == 'on':
                        DbCmd("UPDATE openings SET user = ? WHERE user = ?", (username, self.client_address[0]) )
                
                self.user = username
                          
                response['status'] = 'OK'
                response['message'] = 'Registrazione effettuata'

            self.content_type = 'application/json'
            self.content = json.dumps(response)

    def open(self):
        """Apertura porta"""
        global LAST_OPEN, LAST_OPENER, OPENERS

        # acquisisco il lock
        GLOCK.acquire()

        # chiamata oltre il tempo di IDLE_TIME dall'ultima apertura: è il vincitore
        if self.now > LAST_OPEN + config.IDLE_TIME:
            # aggiorno tutte le global che gestiscono QUESTO giro di gara
            LAST_OPEN = self.now
            LAST_OPENER = self.user
            OPENERS = []
            self.winner = 1
            # apro effettivamente la porta
            GPIO.output(config.GPIO_OPEN,GPIO.HIGH)
            time.sleep(config.SHORT_CIRCUIT)
            GPIO.output(config.GPIO_OPEN,GPIO.LOW)
            # registro nel db
            DbCmd("INSERT INTO openings (idopening, user, winner, datetime, ip) VALUES (?,?,?,?,?)", 
                (self.time2sql(LAST_OPEN), self.user, 1, self.time2sql(LAST_OPEN), self.client_address[0]) )
            # registro l'utente tra i partecipanti
            OPENERS.append(self.user)
        # il vincitore richiama di nuovo l'apertura: BASTA
        elif LAST_OPENER == self.user:
            self.winner = 2
        # un altro partecipante
        elif self.user not in OPENERS:
            # registro la chiamata
            DbCmd("INSERT INTO openings (idopening, user, winner, datetime, ip) VALUES (?,?,?,?,?)", 
                (self.time2sql(LAST_OPEN), self.user, 0, self.time2sql(self.now), self.client_address[0]) )
            OPENERS.append(self.user)
            # se la chiamata avviene entro config.RATE_TIME secondi assegno i punti
            if self.now < LAST_OPEN + config.RATE_TIME:
                DbCmd("UPDATE openings SET points = 1 WHERE idopening = ? AND winner = 1 and points = 0", 
                    (self.time2sql(LAST_OPEN),) )
                DbCmd("UPDATE openings SET points = points + 1 WHERE idopening = ? AND datetime <= ?", 
                    (self.time2sql(LAST_OPEN), self.time2sql(self.now)) )
        # rilascio il lock
        GLOCK.release()

        if self.winner == 1:
            play_message("Ha aperto la porta: %s!" % self.user, basedir + '/static/audio/cache/')

        response = dict(winner=self.winner,lastopener=LAST_OPENER,lastopen=self.time2sql(LAST_OPEN))

        if 'x-requested-with' in self.headers:
            # richiesta via Ajax
            self.content_type = 'application/json'
            self.content = json.dumps(response)
        else:
            # richiesta via finestra normale
            self.template_vars.update(response)
            self.content_type = 'text/html'
            self.content = self.render_template('open.html')

    def rank(self):
        """Visualizzazione classifica"""
        # faccio il parsing della query string
        qs = cgi.urlparse.parse_qs(self.url.query)
        wrank = 'day'
        # cerco in qs il parametro r (rank)
        if 'r' in qs:
            wrank = qs['r'][0]
        else:
            # cerco i parametri inizio e fine
            if 's' in qs or 'e' in qs:
                wrank = 'period'

        # ordine di arrivo di un'apertura specifica
        if wrank == 'last' or re.search(r'^[0-9]+$',wrank):
            # ultima apertura
            if wrank == 'last':
                if LAST_OPEN == 0:
                    # devo ripescare l'ultima apertura dal db
                    c = DbCmd("SELECT max(idopening) as last_open FROM openings")
                    lastopen = c.get_results()
                    if lastopen:
                        idopening = lastopen[0][0]
                    else:
                        idopening = 0
                else:
                    idopening = self.time2sql(LAST_OPEN)
            # apertura specifica
            else:
                idopening = wrank

            c = DbCmd("SELECT idopening, user, winner, points, datetime, (datetime - idopening) / " + 
                str(config.TIMESTAMP_MULTIPLIER) + " as delay, ip FROM openings WHERE idopening = ? ORDER BY datetime", 
                (idopening,))
            rank = c.get_results()

            # devo anche recuperare la prossima e la precedente apertura
            sql_next = "SELECT idopening FROM openings WHERE idopening > ? ORDER BY idopening ASC LIMIT 1"
            sql_previuos = "SELECT idopening FROM openings WHERE idopening < ? ORDER BY idopening DESC LIMIT 1"
            cn = DbCmd(sql_next,(idopening,))
            cp = DbCmd(sql_previuos,(idopening,))
            on, op = cn.get_results(), cp.get_results()
            on = on[0][0] if on else 0
            op = op[0][0] if op else 0
            response = dict(type='order',rank=rank,on=on,op=op,datetime=idopening,wrank=wrank)

        # lista di tutte le aperture, con paginazione
        elif wrank == 'list':
            page = 1
            ps = 10 # page size
            if 'p' in qs:
                page = int(qs['p'][0])
            offset = (page - 1) * ps

            c = DbCmd("SELECT idopening, user, points FROM openings WHERE winner = 1 \
                ORDER BY idopening DESC LIMIT ? OFFSET ?", (ps,offset) )
            rank = c.get_results()            

            # totale aperture:
            c = DbCmd("SELECT COUNT(*) FROM openings WHERE winner = 1");
            to = c.get_results()
            to = to[0][0] if to else 0
            # page next e previous
            lp = to / ps + 1
            pp, np = None, None
            if page > 1:
                pp =  page - 1
            if page < lp: 
                np = page + 1
            
            response = dict(type='list',rank=rank,np=np,pp=pp,lp=lp, page=page,wrank=wrank)

        # classifiche totali
        else:
            c = DbCmd("SELECT min(datetime) FROM openings");
            ft = c.get_results()
            first_time = sql2time(ft[0][0])

            adesso = time.localtime()
            gsett, gmese, ora, minuto, secondo = adesso[6], adesso[2], adesso[3], adesso[4], adesso[5]

            time_end = time.time()

            if wrank == 'week':
                # (ultimi sette giorni: time_start = time.time() - 3600*24*7)
                # classifica della settimana (da lunedì alle 00:00:00)
                time_start = time.time() - gsett*86400 - 3600*ora - 60*minuto - secondo
            elif wrank == 'month':
                # (ultimi 30 giorni: time_start = time.time() - 3600*24*30)
                # classifica del mese 
                time_start = time.time() - (gmese - 1)*86400 - 3600*ora - 60*minuto - secondo
            elif wrank == 'total':
                # classifica totale
                time_start = 0
            elif wrank == 'period':
                # periodo specifico
                time_start = 0
                # inizio e fine
                if 's' in qs:
                    anno_s,mese_s,giorno_s = [int(x) for x in qs['s'][0].split('-')]
                    time_start = time.mktime((anno_s,mese_s,giorno_s,0,0,0,0,0,-1))
                if 'e' in qs:
                    anno_e,mese_e,giorno_e = [int(x) for x in qs['e'][0].split('-')]
                    time_end = time.mktime((anno_e,mese_e,giorno_e,23,59,59,0,0,-1)) + 0.999
            else:
                # classifica del giorno 
                time_start = time.time() - 3600*ora - 60*minuto - secondo

            # indietro oltre il tempo di inizio del Raspberry non si va
            if first_time > time_start:
                time_start = first_time

            sql = "SELECT sum(points) AS score, sum(sign(winner*points)) AS wins, sum(sign(points)) AS goodruns, \
            sum(winner) as wins, count(*) as runs, user FROM openings WHERE datetime >= ? AND datetime < ? \
            GROUP BY user ORDER BY sum(points) DESC, sum(sign(winner*points)) DESC, sum(sign(points)) DESC"
            params = (self.time2sql(time_start),self.time2sql(time_end))
    
            c = DbCmd(sql,params)
            rank = c.get_results()

            response = dict(type='rank',rank=rank,fromdate=time_start,todate=time_end,wrank=wrank)

        if 'x-requested-with' in self.headers:
            # richiesta via Ajax
            self.content_type = 'application/json'
            self.content = json.dumps(response)
        else:
            # richiesta via finestra normale
            self.template_vars.update(response)
            self.content_type = 'text/html'
            self.content = self.render_template('rank.html')
              

    def tail(self):
        """Prende le ultime LAST_LINES righe del file di log"""
        p = os.popen('tail -%s %s' % (config.LAST_LINES, LOG_FILE_WIN),"r")
        data = p.read().decode('utf-8')
        p.close()
        return data

    def render_template(self, template_name):
        """template rendering"""
        tpl = jinja_env.get_template(template_name)
        return tpl.render(self.template_vars).encode('utf-8')

    def serve_static(self):
        """Gestisce le richieste per file statici con
        un meccanismo di cache basato sulle intestazioni HTTP 
        last-modified e if-modified-since"""
        f = None

        path = basedir + self.url.path
        if os.path.isfile(path):
            try:
                f = open(path, 'rb')
            except IOError:
                self.send_error(404)
                return None
            # confronta la data di modifica del file con eventuale If-Modified-Since
            # inviata dal browser (serve un 304 condizionale)
            fs = os.fstat(f.fileno())
            last_modified = int(fs.st_mtime)
            if_modified_since = 0
            if 'if-modified-since' in self.headers:
                if_modified_since = timegm(parsedate(self.headers['if-modified-since']))

            if last_modified > if_modified_since:
                # il file è modificato (oppure il browser non ce l'ha in cache)
                self.send_response(200)
                self.send_header("Content-Type", self.guess_type(path))
                fs = os.fstat(f.fileno())
                self.send_header("Content-Length", str(fs[6]))
                self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
                self.send_header("Expires", self.date_time_string(time.time()+config.STATIC_CACHE))
                self.end_headers()
                shutil.copyfileobj(f, self.wfile)
            else:
                # la copia cache del browser è ok
                self.send_response(304)

            f.close()

        else:
            self.send_error(404)
            return None
    
    def guess_type(self, path):
        """determina il mime type di un file dall'estensione"""
        base, ext = os.path.splitext(path)
        ext = ext.lower()
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        else:
            return 'application/octet-stream'

    def time2sql(self,time):
        return int(round( (time - config.TIMESTAMP_OFFSET) * config.TIMESTAMP_MULTIPLIER ))
        
def play_message(message,cachedir='./'):
    """suona un messaggio (google translate tts + cache)"""
    message = message.encode('utf-8')
    file_sound = cachedir + md5(message).hexdigest() + '.mp3'
    if os.path.isfile(file_sound):
        # suono il file cachato
        os.system("mpg123 -q %s &" % file_sound)
    else:      
        # recupero da google, suono e cacho
        quoted_message = cgi.urllib.quote(message)
        # necessito di un UA vero altrimenti Google TTS ha problemi di charset
        ua = "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:29.0) Gecko/20100101 Firefox/29.0"
        os.system('wget --user-agent="%s" -q "http://translate.google.com/translate_tts?tl=it&q=%s" -O %s && mpg123 -q %s &' % (ua, quoted_message, file_sound, file_sound))


def valid_ip(address):
    try:
        host_bytes = address.split('.')
        valid = [int(b) for b in host_bytes]
        valid = [b for b in valid if b >= 0 and b<=255]
        return len(host_bytes) == 4 and len(valid) == 4
    except:
        return False

def _sign(val):
    if val:
        if val > 0: return 1
        else: return -1
    else:
        return val

def sql2time(sqltime):
    return (float(sqltime) / config.TIMESTAMP_MULTIPLIER) + config.TIMESTAMP_OFFSET

def format_datetime(timestamp,format="%X %x"):
    try:
        locale.setlocale(locale.LC_TIME, "it_IT.UTF8")
        return datetime.fromtimestamp(timestamp).strftime(format).decode('utf8')
        #return time.strftime(format,time.localtime(timestamp)).decode('utf8')
    except:
        return 'Undefined'

def format_sqltime(sqltime,format="%X %x"):
    try:
        return format_datetime(sql2time(sqltime),format)
    except:
        return 'Undefined'

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Gestisce ogni richiesta client HTTP in un thread separato."""

class DbCmd:
    """Classe che implementa i comandi SQL e consente di recuperare eventuali dati in comunicazione con 
    il thread che gestisce il DB SQLite. In pratica è il client SQL"""
    def __init__(self, sql, params=()):
        self.sql = sql
        self.params = params
        self.res_queue = Queue()
        DBQueue.put(self)

    def get_results(self):
        return self.res_queue.get()

class DbServer(threading.Thread):
    """Classe che gestisce la connessione verso il database SQLite tramite un thread separato e 
    esegue le query per conto dei vari thread HTTP tramite la classe DbCmd con code consumer/producer. 
    In pratica fa da server SQL (DbCmd implementa il client) gestendo tutti i comandi SQL verso il db 
    e impedendo un accesso concorrente al database SQLite"""
    def __init__(self,db):
        threading.Thread.__init__(self)
        self.daemon = True
        self.db = db
        self.start()

    def run(self):
        # apre la connessione verso il db
        self.conn = sqlite3.connect(self.db)
        self.conn.create_function("sign", 1, _sign)
        cur = self.conn.cursor()
        while True:
            # per sempre... prende un comando dalla coda
            command = DBQueue.get()
            # esegue il comando
            cur.execute(command.sql, command.params)
            # se non è una select fa il commit
            if not command.sql.upper().startswith("SELECT"):
                self.conn.commit()
            # recupera i dati di ritorno
            results = cur.fetchall()
            # li inserisce nella coda dei risultati
            command.res_queue.put(results)

if __name__ == '__main__':

    #USERS = json.load(open(basedir + '/users.json','r'))
    config = json.load(open(basedir + '/config.json','r'))
    config = configClass(**config)
    db = basedir + '/db/apriporta.db'

    jinja_env = Environment(loader=FileSystemLoader(template_path),autoescape=False)
    jinja_env.filters['sqltime'] = format_sqltime
    jinja_env.filters['datetime'] = format_datetime

    # imposto il mixer per suonare sull'uscita analogica
    os.system("amixer cset numid=3 1")
    
    # configura il GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.cleanup()
    GPIO.setup(config.GPIO_OPEN,GPIO.OUT)
    GPIO.output(config.GPIO_OPEN,GPIO.LOW)

    # thread gestione database 
    DBQueue = Queue()
    DbServer(db)
    
    # fa partire il server
    server = ThreadedHTTPServer((config.SERVER_ADDRESS, config.SERVER_PORT), ApriPorta)
    server.serve_forever()
    