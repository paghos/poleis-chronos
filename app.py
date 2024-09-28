from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, abort
from flask_sqlalchemy import SQLAlchemy
import pytz
import smtplib
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
import string
import secrets
import sqlite3
import os
from subprocess import run
from datetime import datetime, timedelta
from flask_mail import Mail, Message
from flask_session import Session
from waitress import serve
from authlib.integrations.flask_client import OAuth
from chronosconf import appConf
from chronosconf import BoAuth
from chronosconf import KIOSKtotem

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'secret'                                   # Set your secret key (random string)
db = SQLAlchemy(app)
app.config['SESSION_TYPE'] = 'filesystem'                   
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True

API_Token = 'none-none-none-token'                          #Change to something secure

app.config['MAIL_SERVER'] = 'smtp.gmail.com'                # Set your SMTP server URL
app.config['MAIL_PORT'] = 587                               # Set your SMTP port
app.config['MAIL_USE_TLS'] = True                           # Use SSL 
app.config['MAIL_USERNAME'] = 'address'                     # Set your smtp username
app.config['MAIL_PASSWORD'] = 'password'                    # Set your smtp password
app.config['MAIL_DEFAULT_SENDER'] = 'send@as.tld'

oauth = OAuth(app)
keycloak = oauth.register(
    "keycloak",
    client_id=appConf.get("OAUTH2_CLIENT_ID"),
    client_secret=appConf.get("OAUTH2_CLIENT_SECRET"),
    client_kwargs={'scope': 'openid email profile'},
    server_metadata_url=f'{appConf.get("OAUTH2_ISSUER")}/.well-known/openid-configuration',
    )


Session(app)



istituzione = istituto = nomelab ="Comune di Macondo"         # Office name
indirizzo_responsabile = "mail@paganosimone.com"              # Manager e-mail
indirizzo_viceresponsabile = "email@paganosimone.com"         # Second manager e-mail
responsabile = "Bob"                                          # Manager name
url = "chronos-url-not-set"                                   # URL of chronos instance

mail = Mail(app)

with app.app_context():
    db.create_all()

def generate_random_code():
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(8))


class Prenotazione(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cognome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    ufficio = db.Column(db.String(100), nullable=False)
    ora_inizio = db.Column(db.String(10), nullable=False)
    ora_fine = db.Column(db.String(10), nullable=False)
    giorno = db.Column(db.String(10), nullable=False)
    descrizione = db.Column(db.String(500), nullable=False)
    codice_identificativo = db.Column(db.String(10), nullable=False)
    codicefiscale = db.Column(db.String(100), nullable=False)
    segnalazione = db.Column(db.String(1000), nullable=True)
    stato=db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.String(19), default=datetime.now().strftime('%d/%m/%Y %H:%M:%S'))

@app.before_request
def check_user_logged_in():
    if request.path in ['/login', '/authorize', '/api/convalida', '/api/kiosk/aggiungi_prenotazione', '/']:
        return
    if 'oauth_token' not in session:
        return redirect('/login')
    
@app.route('/login')
def login():
    nonce = secrets.token_urlsafe()
    session['nonce'] = nonce
    redirect_uri = url_for('authorize', _external=True)
    return keycloak.authorize_redirect(redirect_uri, nonce=nonce)

@app.route('/authorize')
def authorize():
    try:
        token = keycloak.authorize_access_token()
        session['oauth_token'] = token
        nonce = session.pop('nonce', None)
        user_info = keycloak.parse_id_token(token, nonce=nonce)
        print(user_info)
        session['user_name'] = user_info.get('name')
        session['sub'] = user_info.get('sub')
        session['user_email'] = user_info.get('email')
        session['given_name'] = user_info.get('given_name')
        session['family_name'] = user_info.get('family_name')
        session['user_preferred_username'] = user_info.get('preferred_username')
        return redirect(url_for('index'))
    except Exception as e:
        return f"ATTENZIONE! Errore nell'autenticazione, comunicare questo messaggio di errore all'amministratore di sistema.  {e} "

@app.route('/logout')
def logout():
    session.pop('oauth_token', None)  # Rimuovi il token dalla sessione
    session.pop('accesso_consentito', None)
    keycloak_logout_url = f'{appConf.get("OAUTH2_ISSUER")}/protocol/openid-connect/logout'
    client_id = 'account'
    
    logout_url = f"{keycloak_logout_url}?client_id={client_id}"
    return redirect(logout_url)  

@app.route('/', methods=['GET', 'POST'])
def index():
    utente = session.get('user_name')
    idutente = session.get('sub')
    print('sub',idutente)
    return render_template('index.html', nomelab=nomelab, istituto=istituto, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile, user=utente)


@app.route('/aggiungi_prenotazione', methods=['GET', 'POST'])
def aggiungi_prenotazione():
    nome_loggedin = session.get('given_name')
    cognome_loggedin = session.get('family_name')
    email_loggedin = session.get('user_email')
    if request.method == 'POST':

        ufficio = request.form['ufficio']
        giorno = request.form['giorno']
        ora_inizio = request.form['ora_inizio']
        ora_fine = request.form['ora_fine']

        if verifica_sovrapposizione_orari(giorno, ora_inizio, ora_fine, ufficio):
            return redirect(url_for('prenotazione_esistente'))
        
        nome = request.form['nome']
        cognome = request.form['cognome']
        email = request.form['email']
        
        
        descrizione = request.form['descrizione']
        codice_identificativo = generate_random_code()
        codicefiscale = request.form['codicefiscale']

        stato="Prenotato"

        prenotazione = Prenotazione(nome=nome, cognome=cognome, email=email, ufficio=ufficio, ora_inizio=ora_inizio,
                                    ora_fine=ora_fine, giorno=giorno, descrizione=descrizione,
                                    codice_identificativo=codice_identificativo,
                                    codicefiscale=codicefiscale,stato=stato)
        db.session.add(prenotazione)
        db.session.commit()

        ora_inizio_dt = datetime.strptime(ora_inizio, '%H:%M')
        ora_fine_dt = datetime.strptime(ora_fine, '%H:%M')

        if ora_fine_dt <= ora_inizio_dt:
            flash('The end time must be after the start time.', 'error') #ENGTEXT
            return render_template('aggiungi_prenotazione.html')

        durata_prenotazione = ora_fine_dt - ora_inizio_dt

        ora_fine_effettiva = ora_inizio_dt + durata_prenotazione
        
        username = 000
        password = 0000

        message = Message("Prenotazione confermata.", sender="hello@chronos.com", recipients=[email]) #ENGTEXT

        message.html = render_template('email_conferma.html', nome=nome, cognome=cognome, nomelab=nomelab,
                               codice_identificativo=codice_identificativo, giorno=giorno, ufficio=ufficio, codicefiscale=codicefiscale, descrizione=descrizione, username=username, password=password,
                               ora_inizio=ora_inizio, ora_fine=ora_fine, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile)
        
        mail.send(message)
               
        data_eliminazione = request.form['giorno']
        ora_eliminazione = request.form['ora_fine']
        
        data_eliminazione_format = datetime.strptime(data_eliminazione, '%Y-%m-%d').strftime('%d/%m/%Y')

        
        messageresponsabile = Message("Nuova prenotazione", sender="hello@chronos.com", recipients=[indirizzo_responsabile, indirizzo_viceresponsabile]) #ENGTEXT
        messageresponsabile.html = render_template('email_conferma_responsabile.html', nome=nome, cognome=cognome, nomelab=nomelab,
                               codice_identificativo=codice_identificativo, giorno=giorno, ufficio=ufficio, codicefiscale=codicefiscale, descrizione=descrizione, username=username, password=password,
                               ora_inizio=ora_inizio, ora_fine=ora_fine, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile)

        mail.send(messageresponsabile)
   
        flash('Prenotazione aggiunta con successo.', 'success') #ENGTEXT
        return redirect(url_for('prenotazione_confermata'))

    return render_template('aggiungi_prenotazione.html', nome_loggedin=nome_loggedin, cognome_loggedin=cognome_loggedin, email_loggedin=email_loggedin)

def verifica_sovrapposizione_orari(giorno, ora_inizio, ora_fine, ufficio):
    ora_inizio_obj = datetime.strptime(ora_inizio, '%H:%M').time()
    ora_fine_obj = datetime.strptime(ora_fine, '%H:%M').time()

    prenotazioni = Prenotazione.query.filter(
        Prenotazione.giorno == giorno,
        Prenotazione.ufficio == ufficio
    ).all()

    for prenotazione in prenotazioni:
        pren_ora_inizio_obj = datetime.strptime(prenotazione.ora_inizio, '%H:%M').time()
        pren_ora_fine_obj = datetime.strptime(prenotazione.ora_fine, '%H:%M').time()

        if (ora_inizio_obj < pren_ora_fine_obj and ora_fine_obj > pren_ora_inizio_obj):
            return True

    return False

@app.route('/prenotazione_esistente', methods=['GET'])
def prenotazione_esistente():
    prenotazioni = Prenotazione.query.order_by(Prenotazione.timestamp).all()
    return render_template('prenotazione_esistente.html', prenotazioni=prenotazioni, nomelab=nomelab)

@app.route('/backoffice_preauth', methods=['GET', 'POST'])
def backoffice():
    user_sub = session.get('sub')
    if user_sub not in BoAuth['allowed_subs']:
        return render_template('accesso_backoffice_fallito.html',sub=user_sub), 403
    if request.method == 'POST':
        password_inserita = request.form['password']
        admin_token="unused_setting"
        if password_inserita == admin_token:

            session['accesso_consentito'] = True
            message = Message("New login detected", sender="hello@chronos.com", recipients=[indirizzo_responsabile]) #ENGTEXT

            message.html = render_template('email_login.html', nomelab=nomelab, responsabile=responsabile, url=url)
            
            mail.send(message)
            return redirect('/visualizza')
        else:
            flash('Token amministratore errato', 'danger') #ENGTEXT
    return render_template('password.html')


@app.route('/visualizza', methods=['GET'])
def visualizza_prenotazioni():
    user_sub = session.get('sub')
    user = session.get('user_name')
    email = session.get('user_email')
    print(user, email)
    if user_sub not in BoAuth['allowed_subs']:
        return render_template('accesso_backoffice_fallito.html', sub=user_sub, user=user, email=email), 403
    else:
        prenotazioni = Prenotazione.query.order_by(Prenotazione.giorno).all()
        return render_template('visualizza.html', prenotazioni=prenotazioni, user=user, email=email)
        

@app.route('/registro_pubblico', methods=['GET'])
def registro_pubblico_prenotazioni():
    prenotazioni = Prenotazione.query.order_by(Prenotazione.timestamp).all()
    return render_template('registro_pubblico.html', prenotazioni=prenotazioni)

@app.route('/recupera_prenotazione', methods=['GET', 'POST'])
def recupera_prenotazione():
    if request.method == 'POST':
        codice_identificativo = request.form['codice_identificativo']

        prenotazione = Prenotazione.query.filter_by(codice_identificativo=codice_identificativo).first()

        return render_template('recupera_prenotazione.html', prenotazione=prenotazione)

    return render_template('recupera_prenotazione.html')

@app.route('/convalida', methods=['GET', 'POST'])
def convalida():
    if request.method == 'POST':
        codice_identificativo = request.form.get('codice_identificativo')
        prenotazione = Prenotazione.query.filter_by(codice_identificativo=codice_identificativo).first()
        print("--------------PRENOTAZIONE ",codice_identificativo,"--------------")
        if prenotazione:
            today_date = datetime.now().strftime("%Y-%m-%d")
            giornoprenotazione = prenotazione.giorno  # Assumendo che sia già nel formato corretto
            
            ora_attuale = datetime.now()
            
            # Print di debug
            print(f"Data odierna: {today_date}")
            print(f"Data prenotazione: {giornoprenotazione}")
            print(f"Orario attuale: {ora_attuale}")

            if giornoprenotazione == today_date:
                try:
                    orainizio = datetime.strptime(prenotazione.ora_inizio, "%H:%M")
                    # Combinare data e ora per la prenotazione
                    orainizio_completo = datetime.combine(datetime.strptime(giornoprenotazione, "%Y-%m-%d"), orainizio.time())
                except ValueError as e:
                    print(f"Errore nel parsing dell'ora: {e}")
                    return render_template('convalida_nontrovata.html')

                intervallo = timedelta(minutes=10)
                # Print di debug per l'intervallo
                print(f"Orario inizio prenotazione: {orainizio_completo}")
                print(f"Intervallo di validazione: {orainizio_completo - intervallo} - {orainizio_completo + intervallo}")

                if orainizio_completo - intervallo <= ora_attuale <= orainizio_completo + intervallo:
                    prenotazione.stato = "Validato"
                    db.session.commit()
                    return render_template('convalida_successo.html')
                else:
                    print(f"Orario attuale {ora_attuale} non rientra nell'intervallo {orainizio_completo - intervallo} - {orainizio_completo + intervallo}.")
                    return render_template('convalida_fuoritempo.html')
            else:
                print("Data della prenotazione non corrisponde alla data odierna.")
                return render_template('convalida_nonodierna.html')
        else:
            print("Prenotazione non trovata.")
            return render_template('convalida_nontrovata.html')
    
    return render_template('convalida.html')

@app.route('/elimina_prenotazione', methods=['POST'])
def elimina_prenotazione():
    if request.method == 'POST':
        id_prenotazione = request.form.get('id_prenotazione')
        prenotazione = Prenotazione.query.filter_by(id=id_prenotazione).first()

        if prenotazione:

            codice_identificativo=prenotazione.codice_identificativo
            nome=prenotazione.nome
            cognome=prenotazione.cognome
            email=prenotazione.email
            ufficio=prenotazione.ufficio
            ora_inizio=prenotazione.ora_inizio
            ora_fine=prenotazione.ora_fine
            giorno=prenotazione.giorno
            descrizione=prenotazione.descrizione
            codice_identificativo=prenotazione.codice_identificativo
            codicefiscale=prenotazione.codicefiscale
            
            message = Message("Prenotazione cancellata", sender="hello@chronos.com", recipients=[email]) #ENGTEXT
            message.html = render_template('email_annullata.html', nome=nome, cognome=cognome, nomelab=nomelab,
                                giorno=giorno, ufficio=ufficio, codicefiscale=codicefiscale, descrizione=descrizione,
                                ora_inizio=ora_inizio, ora_fine=ora_fine, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile)
            
            mail.send(message)
        

            username = "lab"+prenotazione.codice_identificativo

        
            

            
            messageresponsabile = Message("Prenotazione cancellata", sender="hello@chronos.com", recipients=[indirizzo_responsabile, indirizzo_viceresponsabile]) #ENGTEXT
            messageresponsabile.html = render_template('email_annullata_responsabile.html', nome=nome, cognome=cognome, nomelab=nomelab,
                               giorno=giorno, ufficio=ufficio, codicefiscale=codicefiscale, descrizione=descrizione,
                               ora_inizio=ora_inizio, ora_fine=ora_fine, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile)

            mail.send(messageresponsabile)
            
            db.session.delete(prenotazione)
            db.session.commit()
            return redirect(url_for('prenotazione_cancellata'))
        else:
            flash('La prenotazione non esiste.', 'danger')

    return redirect('/recupera_prenotazione')

@app.route('/prenotazione_confermata')
def prenotazione_confermata():
    return render_template('prenotazione_confermata.html', indirizzo_responsabile=indirizzo_responsabile)

@app.route('/regolamento')
def regolamento():
    return render_template('regolamento.html')

@app.route('/kiosk')
def kiosk():
    
    return render_template('kiosk.html',istituzione=istituzione)

@app.route('/prenotazione_cancellata')
def prenotazione_cancellata():
    return render_template('prenotazione_cancellata.html', indirizzo_responsabile=indirizzo_responsabile)

@app.route('/segnalazione', methods=['GET', 'POST'])
def segnalazione():
    if request.method == 'POST':
        codice_identificativo = request.form['codice_identificativo']
        segnalazione_testo = request.form['segnalazione']

        prenotazione = Prenotazione.query.filter_by(codice_identificativo=codice_identificativo).first()

        if prenotazione:
            prenotazione.segnalazione = segnalazione_testo
            db.session.commit()
            flash('Segnalazione aggiunta con successo.', 'success')

            codice_identificativo=prenotazione.codice_identificativo
            nome=prenotazione.nome
            cognome=prenotazione.cognome
            email=prenotazione.email
            ufficio=prenotazione.ufficio
            ora_inizio=prenotazione.ora_inizio
            ora_fine=prenotazione.ora_fine
            giorno=prenotazione.giorno
            descrizione=prenotazione.descrizione
            codice_identificativo=prenotazione.codice_identificativo
            codicefiscale=prenotazione.codicefiscale
            segnalazione=prenotazione.segnalazione
            
            message = Message("Hai inviato una segnalazione", sender="hello@chronos.com", recipients=[email]) #ENGTEXT
            message.html = render_template('email_segnalazione.html', nome=nome, cognome=cognome, nomelab=nomelab,
                                giorno=giorno, ufficio=ufficio, codicefiscale=codicefiscale, descrizione=descrizione,
                                ora_inizio=ora_inizio, ora_fine=ora_fine, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile, segnalazione=segnalazione)
            
            mail.send(message)
            
            
            messageresponsabile = Message("Nuova segnalazione ricevuta", sender="hello@chronos.com", recipients=[indirizzo_responsabile, indirizzo_viceresponsabile]) #ENGTEXT
            messageresponsabile.html = render_template('email_segnalazione_responsabile.html', nome=nome, cognome=cognome, nomelab=nomelab,
                                giorno=giorno, ufficio=ufficio, codicefiscale=codicefiscale, descrizione=descrizione,
                                ora_inizio=ora_inizio, ora_fine=ora_fine, responsabile=responsabile, indirizzo_responsabile=indirizzo_responsabile, segnalazione=segnalazione)
            
            mail.send(messageresponsabile)
            

        else:
            flash('La prenotazione con il codice identificativo specificato non esiste.', 'danger')

    return render_template('segnalazione.html')

@app.route('/carica_prenotazione', methods=['GET'])
def carica_prenotazione():
    codice_identificativo = request.args.get('codice_identificativo')

    prenotazione = Prenotazione.query.filter_by(codice_identificativo=codice_identificativo).first()

    if prenotazione:
        prenotazione_data = {
            'nome': prenotazione.nome,
            'cognome': prenotazione.cognome,
            'email': prenotazione.email,
            'ufficio': prenotazione.ufficio,
            'segnalazione': prenotazione.segnalazione,
        }
        return jsonify(prenotazione_data)
    else:
        return jsonify({'error': 'Prenotazione non trovata'}), 404

@app.route('/upcoming_reservations')
def upcoming_reservations():
    now = datetime.now()
    two_hours_later = now + timedelta(hours=2)
    
    current_time_str = now.strftime('%H:%M')
    current_date_str = now.strftime('%Y-%m-%d')
    two_hours_later_str = two_hours_later.strftime('%H:%M')
    
    prenotazioni = Prenotazione.query.filter(
        Prenotazione.giorno == current_date_str,
        Prenotazione.ora_inizio >= current_time_str,
        Prenotazione.ora_inizio <= two_hours_later_str
    ).order_by(Prenotazione.ora_inizio).all()
    
    return render_template('upcoming_reservations.html', prenotazioni=prenotazioni)

@app.route('/api/convalida', methods=['GET', 'POST'])
def api_convalida():
    remote_user = request.args.get('authenticate-as')
    remote_identity = request.args.get('identity')
    remote_prenotazione = request.args.get('prenotazione')
    remote_apitoken = request.args.get('api-token')

    if remote_apitoken == API_Token and remote_user in BoAuth['allowed_subs']:
        pass
    else:
        return "Uhm... Nope!", 403
    
    if request.method == 'POST':
        print(remote_user, " - ", remote_identity, " - Prenotazione_", remote_prenotazione, " | Ha utilizzato le API per convalidare una prenotazione")
        prenotazione = Prenotazione.query.filter_by(codice_identificativo=remote_prenotazione).first()
        if prenotazione:
                remote_prenotazione_original_status=prenotazione.stato
                prenotazione.stato = "Completo"
                remote_prenotazione_new_status = prenotazione.stato
                db.session.commit()
                return f"Prenotazione {remote_prenotazione} passa da {remote_prenotazione_original_status} a {remote_prenotazione_new_status}."
        else:
            return "ERRORE! Impossibile trovare una prenotazione con questo codice identificativo. Verificare la corretta immissione dello stesso."
    return "Necessaria diagnostica."

@app.route('/api/prenotazione_confermata', methods=['GET'])
def api_prenotazione_confermata():
    retrieved_idprenotazione=request.args.get('idprenotazione')
    prenotazione = retrieved_idprenotazione
    return render_template('pren_confermata.html', prenotazione=prenotazione)

@app.route('/api/kiosk/prenotazione_confermata', methods=['GET'])
def api_kiosk_prenotazione_confermata():
    retrieved_idprenotazione=request.args.get('idprenotazione')
    prenotazione = retrieved_idprenotazione
    return render_template('kiosk_pren_confermata.html', prenotazione=prenotazione)

@app.route('/api/kiosk/aggiungi_prenotazione', methods=['GET', 'POST'])
def api_aggiungi_prenotazione():
    retrieved_ufficio=request.args.get('ufficio')

    
    if request.method == 'POST':
        nome='Prenotazione TOTEM'
        cognome='Anagrafica sconosciuta'
        codicefiscale='CFSCONOSCIUTOXXX'
        email='no-email'
        descrizione='Prenotazione effettuata tramite Totem'
        codice_identificativo = 'KK'+generate_random_code() #KK Prefix is used for reservations in Kiosk Mode
        stato='Validato'
        giorno=datetime.now().strftime("%Y-%m-%d")
        ora_inizio = datetime.now()

        ora_inizio_truncated = ora_inizio.replace(second=0, microsecond=0)

        ora_fine = ora_inizio_truncated + timedelta(hours=3)

        ora_inizio_str = ora_inizio_truncated.strftime("%H:%M")
        ora_fine_str = ora_fine.strftime("%H:%M")
        ufficio=retrieved_ufficio
        prenotazione = Prenotazione(nome=nome, cognome=cognome, email=email, ufficio=ufficio, ora_inizio=ora_inizio_str,
                                    ora_fine=ora_fine_str, giorno=giorno, descrizione=descrizione,
                                    codice_identificativo=codice_identificativo,
                                    codicefiscale=codicefiscale,stato=stato)
        db.session.add(prenotazione)
        db.session.commit()
    return redirect(f'/api/kiosk/prenotazione_confermata?idprenotazione={codice_identificativo}'),301


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
