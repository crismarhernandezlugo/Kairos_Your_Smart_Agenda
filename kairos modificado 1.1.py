import sqlite3
import pytz
import asyncio
import re
from groq import Groq
from datetime import datetime
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

# --- ⚙️ CONFIGURACIÓN ---
TOKEN_TELEGRAM = '8336273614:AAGbS_2xJe9yNE8Shn1Srwfy8wzuheQNYug'
API_KEY_GROQ = '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'
ZONA_HORARIA = pytz.timezone('America/Caracas') 

# --- INICIALIZACIÓN ---
client_groq = Groq(api_key=API_KEY_GROQ)

# --- 🗄️ GESTIÓN DE BASE DE DATOS ---
def inicializar_db():
    conn = sqlite3.connect('kairos.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS agenda 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  chat_id TEXT, fecha TEXT, hora TEXT, 
                  tarea TEXT, avisado INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historial 
                 (user_id TEXT, msg_user TEXT, msg_bot TEXT, timestamp DATETIME)''')
    conn.commit()
    conn.close()

# --- 🛠️ LÓGICA DE REGISTRO (MEJORADA) ---
def procesar_agendamiento(chat_id, texto_bot):
    # Buscamos la fecha YYYY-MM-DD y la hora HH:MM
    fecha_m = re.search(r'(\d{4}-\d{2}-\d{2})', texto_bot)
    hora_m = re.search(r'(\d{2}:\d{2})', texto_bot)
    
    if fecha_m and hora_m:
        f = fecha_m.group(1)
        h = hora_m.group(1)
        # Extraemos la descripción después del guion
        t = texto_bot.split("-")[-1].strip() if "-" in texto_bot else "Tarea pendiente"
        
        try:
            conn = sqlite3.connect('kairos.db')
            c = conn.cursor()
            c.execute("INSERT INTO agenda (chat_id, fecha, hora, tarea, avisado) VALUES (?, ?, ?, ?, 0)",
                      (str(chat_id), f, h, t))
            conn.commit()
            conn.close()
            print(f"📌 GUARDADO EXITOSO: {t} para el {f} a las {h}") # Esto saldrá en la pantalla negra
            return True
        except Exception as e:
            print(f"❌ Error al insertar en DB: {e}")
    else:
        print("⚠️ No se encontró formato de fecha/hora en la respuesta del bot.")
    return False

# --- ⏰ RELOJ DE NOTIFICACIONES (CON DIAGNÓSTICO) ---
async def chequear_notificaciones(app):
    print("⏰ Reloj de notificaciones activado...")
    while True:
        try:
            ahora = datetime.now(ZONA_HORARIA)
            f_hoy = ahora.strftime('%Y-%m-%d')
            h_hoy = ahora.strftime('%H:%M')
            
            # Esto imprimirá la hora en tu pantalla negra cada 30 segundos
            print(f"🔎 Revisando agenda... [Hora actual: {h_hoy}]")
            
            conn = sqlite3.connect('kairos.db')
            c = conn.cursor()
            # Buscamos tareas para la fecha y hora exactas que no hayan sido avisadas
            c.execute("SELECT id, chat_id, tarea FROM agenda WHERE fecha = ? AND hora = ? AND avisado = 0", (f_hoy, h_hoy))
            tareas = c.fetchall()
            
            for tid, cid, txt in tareas:
                msg = f"🔔 *¡ATENCIÓN! RECORDATORIO*\n\n🎯 *Tarea:* {txt}\n⏰ *Hora:* {h_hoy}\n\n¡Es el momento!"
                await app.bot.send_message(chat_id=cid, text=msg, parse_mode=ParseMode.MARKDOWN)
                c.execute("UPDATE agenda SET avisado = 1 WHERE id = ?", (tid,))
                print(f"🚀 NOTIFICACIÓN ENVIADA: {txt}")
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ Error en el Reloj: {e}")
        
        await asyncio.sleep(30) # Revisa cada 30 segundos

# --- 💬 MANEJO DE MENSAJES ---
async def manejar_kairos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    uid = str(update.effective_user.id)
    cid = str(update.effective_chat.id)
    ahora = datetime.now(ZONA_HORARIA)
    
    prompt = (
        f"Eres Kairos, una agenda minimalista. Hoy es {ahora.strftime('%Y-%m-%d %H:%M')}.\n"
        "Si el usuario quiere agendar, confirma SIEMPRE al final con: 'CONFIRMADO: [YYYY-MM-DD] [HH:MM] - descripción'."
    )

    try:
        res = client_groq.chat.completions.create(
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": update.message.text}],
            model="llama-3.3-70b-versatile",
        )
        texto = res.choices[0].message.content

        # Si el bot confirma, intentamos guardar
        if "CONFIRMADO:" in texto:
            if procesar_agendamiento(cid, texto):
                texto += "\n\n✅ *Anclado a tu agenda y listo para avisarte.*"
            else:
                texto += "\n\n⚠️ *Error interno: No pude procesar la fecha/hora.*"

        await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"Error IA: {e}")

# --- 🚀 EJECUCIÓN ---
async def main():
    inicializar_db()
    app = ApplicationBuilder().token(TOKEN_TELEGRAM).build()
    
    app.add_handler(CommandHandler('start', lambda u,c: u.message.reply_text("✅ *Kairos en línea.*")))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_kairos))
    
    # IMPORTANTE: Esto lanza el reloj
    asyncio.create_task(chequear_notificaciones(app))
    
    print("🚀 BOT INICIADO Y ESCUCHANDO...")
    
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        while True: await asyncio.sleep(10)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except:
        print("Bot apagado.")
