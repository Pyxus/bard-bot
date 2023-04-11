import os
import discord
import re
import yt_dlp
from dataclasses import dataclass
from discord.ext import tasks
import asyncio

TOKEN = os.getenv('DISCORD_TOKEN')
YT_PATTERN = re.compile(r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w\-]{11}')
FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
YDL_OPTS = {
	'format': 'm4a/bestaudio/best',
	'outtmpl': f'%(title)s.%(ext)s',
	'postprocessors': [{  # Extract audio using ffmpeg
		'key': 'FFmpegExtractAudio',
		'preferredcodec': 'mp3',
	}]
}

def main():
	intents = discord.Intents.default()
	intents.message_content = True
	client = Client(intents = intents)
	client.run(TOKEN)

@dataclass
class Song:
	name: str
	url: str

# Doesn't make sense for the view to have all this logic
# Should just have call backs that respond to interactions
class MusicView(discord.ui.View):
	control_msg: discord.Message
	voice_client: discord.VoiceClient
	song_queue: list[Song]
	current_song: Song
	is_looping: bool

	def __init__(self, voice_client: discord.VoiceClient):
		super().__init__()
		self.voice_client = voice_client
		self.control_msg = None
		self.song_queue = []
		self.current_song = None
		self.is_looping = False


	async def add_song(self, song: Song):
		self.song_queue.append(song)

		if self.current_song != None:
			await self.control_msg.edit(content=f"**Now Playing:** {self.current_song.name}\n**Queue Size: ** {len(self.song_queue)}")
	

	async def play_next(self):
		if len(self.song_queue) > 0:
			self.current_song = self.song_queue.pop(0)
			await self.play_current_song()
		else:
			self.current_song = None


	def can_play_next(self):
		return not self.is_looping and not self.voice_client.is_playing()

	
	def can_loop(self):
		return (
			self.is_looping 
			and not self.voice_client.is_playing()
			and not self.voice_client.is_paused()
			)

	async def play_after(self, error):
		if error:
			print("Error playing next song!")
		print("Test_IsPlaying: ", self.voice_client.is_playing())
		print("Test_IsPaused: ", self.voice_client.is_paused())
		if self.is_looping:
			await self.play_current_song()
		else:
			await self.play_next()

	async def play_source(self, source):
			self.voice_client.stop()
			try:
				self.voice_client.play(
					source,
					after=lambda e: asyncio.run_coroutine_threadsafe(self.play_after(e), self.voice_client.loop)
					)
			except (discord.errors.ClientException, discord.errors.OpusNotLoaded) as e:
				print(f"Error playing audio: {e}")
				await asyncio.sleep(1)
				await self.play_source(source)


	async def play_current_song(self):
		if self.voice_client.is_connected() and self.current_song != None:
			print(f"**Now Playing:** {self.current_song.name}")
			await self.control_msg.clear_reaction("⏸")
			await self.control_msg.add_reaction("▶")
			await self.control_msg.edit(content=f"**Now Playing:** {self.current_song.name}\n **Queue Size: ** {len(self.song_queue)}")
			self.voice_client.stop()
			source = await discord.FFmpegOpusAudio.from_probe(self.current_song.url, **FFMPEG_OPTIONS)
			await self.play_source(source=source)
	

	async def stop(self):
		self.voice_client.stop()
		self.song_queue = []
		self.is_looping = False
		await self.control_msg.clear_reactions()
		await self.voice_client.disconnect()


	@discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.grey)
	async def play_pause_button(self,  button: discord.ui.Button, interaction: discord.Interaction):
		if self.voice_client.is_paused():
			await self.control_msg.clear_reaction("⏸")
			await self.control_msg.add_reaction("▶")
			print("Song resumed.")
			self.voice_client.resume()
		else:
			await self.control_msg.clear_reaction("▶")
			await self.control_msg.add_reaction("⏸")
			print("Song paused.")
			self.voice_client.pause()
		
		await interaction.response.defer()
	

	@discord.ui.button(emoji="⏹", style=discord.ButtonStyle.grey)
	async def stop_button(self, button: discord.ui.Button, interaction: discord.Interaction):
		await self.stop()
		await interaction.response.defer()


	@discord.ui.button(emoji="⏩", style=discord.ButtonStyle.grey)
	async def skip_button(self, button: discord.ui.Button, interaction: discord.Interaction):
		# Will trigger the after callback causing the next song to play
		self.voice_client.stop()
		await interaction.response.defer()


	@discord.ui.button(emoji="🔁", style=discord.ButtonStyle.grey)
	async def repeat_button(self, button: discord.ui.Button, interaction: discord.Interaction):
		self.is_looping = not self.is_looping

		if self.is_looping:
			await self.control_msg.add_reaction("🔁")
		else:
			await self.control_msg.clear_reaction("🔁")

		await interaction.response.defer()


class Client(discord.Client):
	current_music_view: MusicView = None

	async def on_ready(self):
		print(f'Logged on as {self.user}!')
		#self.on_process.start()

	@tasks.loop(seconds=2)
	async def on_process(self):
		pass


	async def on_message(self, message: discord.Message):
		if message.author.id == self.user.id:
			return

		print(f'Message from {message.author}: {message.content}')

		text_channel = self.get_channel(message.channel.id)
		voice_channel = message.author.voice.channel
		songs = []

		# Check for YT URL
		if len(message.content) > 0:
			search_result = YT_PATTERN.search(message.content)

			if search_result:
				yt_link = search_result.group(0)

				with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
					yt_info = ydl.extract_info(yt_link, download=False)
					yt_info['ext'] = 'mp3'
					filename = ydl.prepare_filename(yt_info)
					songs.append(Song(name=filename, url=yt_info['url']))
		
		# Check for MP3
		for attachment in message.attachments:
			print(attachment.content_type)
			if attachment.content_type == "audio/mpeg":
				songs.append(Song(name=attachment.filename, url=attachment.url))
		
		# Queue all discovered songs
		for song in songs:
			await self.queue_song(
				text_channel=text_channel, 
				voice_channel=voice_channel,
				song=song
				)
		
		if len(songs) > 0:
			await message.delete()

	async def save_attachment(self, attachment, fp: str):
		os.makedirs(os.path.dirname(fp), exist_ok=True)
		await attachment.save(fp=fp)
	

	async def queue_song(self, 
		      text_channel: discord.abc.GuildChannel, 
			  voice_channel,
			  song: Song,
			  ):
		if not self.is_view_connected():
			voice_client = await voice_channel.connect()

			self.current_music_view = MusicView(voice_client=voice_client)
			self.current_music_view.timeout = None
			self.current_music_view.control_msg = await text_channel.send(
				view=self.current_music_view, 
				content=f"Now Playing...")
			await self.current_music_view.add_song(song)
			await self.current_music_view.play_next()

		else:
			await self.current_music_view.add_song(song)
			if not self.current_music_view.voice_client.is_playing():
				await self.current_music_view.play_next()
			#await channel.send(content=f"{attachment.filename} added to queue!")
	

	def download_yt(self, links: list[str]):
		with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
			error_code = ydl.download(links)

	def is_view_connected(self):
		return (
				self.current_music_view != None
				and self.current_music_view.voice_client != None
				and self.current_music_view.voice_client.is_connected()
				)

if __name__ == "__main__":
	main()