import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import pytz
from flask import Flask
from threading import Thread

# Configuración del bot
TOKEN = "MTI4NjM3NjU3ODE2MjM2NDQ5Ng.G2sMIp.6y5oExmLCxWp-tX_P1DuOMqQ2xCvWizqDCfA9I"
MAX_LIMIT = 5000  # Límite máximo de objetos
CHANNEL_ID = 1319817672682373120  # ID del canal principal (embed fijo)
NOTIFICATION_CHANNEL_ID = 1319808831055990946  # ID del canal para notificaciones importantes

# Inicialización del bot
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Variables
total_count = 0
embed_message = None  # Mensaje del embed que se actualizará
registro_ventas = [
]  # Lista para mantener un registro de quién vendió, cuánto y cuándo
proximo_reinicio = None  # Variable para el próximo reinicio

# Horarios de reinicio (en horario español peninsular)
REINICIO_HORARIOS = ["03:00", "11:00", "19:00"]


@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")
    bot.loop.create_task(
        programar_reinicios())  # Inicia los reinicios automáticos
    await iniciar_embed_fijo(
    )  # Envía el embed fijo al canal al iniciar el bot


async def iniciar_embed_fijo():
    """Envía un embed fijo al canal y lo guarda para futuras actualizaciones."""
    global embed_message
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print(f"No se encontró el canal con ID: {CHANNEL_ID}")
        return

    embed = discord.Embed(
        title="Seguimiento de Ventas",
        description=
        f"Total actual: **{total_count}/{MAX_LIMIT}**\n\nHaz clic en el botón para sumar.",
        color=discord.Color.blue(),
    )

    view = SumarView()  # Botones interactivos
    if embed_message is None:
        embed_message = await channel.send(embed=embed, view=view
                                           )  # Envía el mensaje inicial
    else:
        await embed_message.edit(embed=embed, view=view
                                 )  # Actualiza el mensaje si ya existe


class SumarView(discord.ui.View):

    def __init__(self):
        super().__init__()

    @discord.ui.button(label="Sumar", style=discord.ButtonStyle.primary)
    async def sumar_button(self, interaction: discord.Interaction,
                           button: discord.ui.Button):
        """Maneja el clic en el botón de sumar."""
        global total_count

        # Verifica si el total ya alcanzó el límite
        if total_count >= MAX_LIMIT:
            embed = discord.Embed(
                title="Límite alcanzado",
                description=
                f"El total de {MAX_LIMIT} objetos ha sido alcanzado. No se pueden sumar más objetos hasta el próximo reinicio.",
                color=discord.Color.red())
            await interaction.response.send_message(embed=embed,
                                                    ephemeral=True)
            return

        await interaction.response.send_message(
            "Por favor, escribe la cantidad que quieres sumar en el chat.",
            ephemeral=True)

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            # Espera la respuesta del usuario
            msg = await bot.wait_for("message", check=check, timeout=30.0)
            cantidad = int(msg.content)

            # Borra el mensaje del usuario
            await msg.delete()

            if cantidad <= 0:
                await interaction.followup.send(
                    "Por favor, ingresa una cantidad positiva.",
                    ephemeral=True)
                return

            if total_count + cantidad > MAX_LIMIT:
                await interaction.followup.send(
                    f"No puedes agregar esa cantidad porque excede el límite máximo de {MAX_LIMIT}.",
                    ephemeral=True)
                return

            total_count += cantidad
            registro_ventas.append(
                (msg.author.name, cantidad,
                 datetime.now(
                     pytz.timezone('Europe/Madrid'))))  # Ajusta la hora a CET

            # Notifica si se alcanza el límite
            if total_count >= MAX_LIMIT:
                await enviar_notificacion_limite()

            # Actualiza el embed fijo
            await actualizar_embed_fijo()

            await interaction.followup.send(
                f"Se sumaron {cantidad} objetos correctamente.",
                ephemeral=True)

        except ValueError:
            await interaction.followup.send(
                "La cantidad ingresada no es un número válido.",
                ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "No respondiste a tiempo. Intenta nuevamente.", ephemeral=True)


async def actualizar_embed_fijo():
    """Actualiza el embed fijo con el nuevo total y muestra el registro de ventas."""
    global embed_message
    channel = bot.get_channel(CHANNEL_ID)
    if embed_message is None or channel is None:
        return

    registro = "\n".join([
        f"{vendedor}: {cantidad} objetos ({fecha.strftime('%d/%m/%Y %H:%M')})"
        for vendedor, cantidad, fecha in registro_ventas
    ])
    if not registro:
        registro = "No hay registros de ventas aún."

    embed = discord.Embed(
        title="Seguimiento de Ventas",
        description=
        f"Total actual: **{total_count}/{MAX_LIMIT}**\n\nHaz clic en el botón para sumar.",
        color=discord.Color.blue(),
    )
    embed.add_field(name="Registro de Ventas", value=registro, inline=False)

    view = SumarView()
    await embed_message.edit(embed=embed,
                             view=view)  # Actualiza el mensaje del embed


async def enviar_notificacion_limite():
    """Envía una notificación al canal de notificaciones importantes con el registro de ventas."""
    notification_channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
    if notification_channel is None:
        print(f"No se encontró el canal con ID: {NOTIFICATION_CHANNEL_ID}")
        return

    registro = "\n".join([
        f"{vendedor}: {cantidad} objetos ({fecha.strftime('%d/%m/%Y %H:%M')})"
        for vendedor, cantidad, fecha in registro_ventas
    ])
    if not registro:
        registro = "No hay registros de ventas."

    embed = discord.Embed(
        title="¡Se alcanzó el límite máximo!",
        description=
        f"Se alcanzó el límite de **{MAX_LIMIT}** objetos.\n\n**Registro de Ventas:**\n{registro}",
        color=discord.Color.red(),
    )
    await notification_channel.send(embed=embed)


async def programar_reinicios():
    """Programa los reinicios automáticos en los horarios definidos."""
    global total_count, registro_ventas, proximo_reinicio
    while True:
        now = datetime.now(pytz.timezone('Europe/Madrid'))
        reinicio_horas = [
            datetime.strptime(h, "%H:%M").replace(
                year=now.year,
                month=now.month,
                day=now.day,
                tzinfo=pytz.timezone('Europe/Madrid'))
            for h in REINICIO_HORARIOS
        ]

        # Encuentra el próximo reinicio
        proximos = [h for h in reinicio_horas if h > now]
        if not proximos:
            proximos = [h + timedelta(days=1) for h in reinicio_horas]

        proximo_reinicio = min(proximos)
        tiempo_restante = (proximo_reinicio - now).total_seconds()

        # Notificación 5 minutos antes del reinicio
        await asyncio.sleep(tiempo_restante - 300)
        notification_channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if notification_channel:
            registro = "\n".join([
                f"{vendedor}: {cantidad} objetos ({fecha.strftime('%d/%m/%Y %H:%M')})"
                for vendedor, cantidad, fecha in registro_ventas
            ]) or "No hay registros."
            await notification_channel.send(
                f"¡El reinicio automático ocurrirá en 5 minutos!\n\n**Registro de Ventas:**\n{registro}"
            )

        # Esperar hasta el reinicio
        await asyncio.sleep(300)

        # Reinicia el total y el registro de ventas
        total_count = 0
        registro_ventas = []
        await actualizar_embed_fijo()


@bot.command()
async def reiniciomanual(ctx):
    """Comando para reiniciar el total manualmente"""
    global total_count, registro_ventas
    total_count = 0
    registro_ventas = []
    await actualizar_embed_fijo()

    # Borra el mensaje del comando
    await ctx.message.delete()

    # Envía el mensaje de reinicio manual y lo elimina después de 10 segundos
    msg = await ctx.send("El total se ha reiniciado manualmente a 0.")
    await asyncio.sleep(10)
    await msg.delete()


@bot.command()
async def borrar(ctx, cantidad: str = None):
    """Comando para borrar mensajes en el canal."""
    # Borra el mensaje del comando
    await ctx.message.delete()

    if cantidad is None:
        msg = await ctx.send(
            "Especifica la cantidad de mensajes a borrar o usa 'todo' para borrar el chat."
        )
        await asyncio.sleep(10)
        await msg.delete()
        return

    if cantidad.lower() == "todo":
        # Borra todos los mensajes en el canal
        await ctx.channel.purge()
        msg = await ctx.send(
            "Todos los mensajes en este canal han sido eliminados.")
        await asyncio.sleep(10)
        await msg.delete()
    else:
        try:
            cantidad = int(cantidad)
            if cantidad <= 0:
                msg = await ctx.send("La cantidad debe ser un número positivo."
                                     )
                await asyncio.sleep(10)
                await msg.delete()
                return

            # Borra la cantidad especificada de mensajes
            await ctx.channel.purge(limit=cantidad)
            msg = await ctx.send(f"Se han borrado {cantidad} mensajes.")
            await asyncio.sleep(10)
            await msg.delete()
        except ValueError:
            msg = await ctx.send(
                "Por favor, ingresa un número válido o usa 'todo'.")
            await asyncio.sleep(10)
            await msg.delete()


# Servidor Flask para mantener Replit activo
app = Flask('')


@app.route('/')
def home():
    return "¡El bot está activo!"


def run():
    app.run(host='0.0.0.0', port=8080)


t = Thread(target=run)
t.start()

# Ejecuta el bot
bot.run(TOKEN)
