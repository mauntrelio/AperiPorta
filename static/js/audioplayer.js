var myPlayer = new Object();
myPlayer.onInit = function(){this.position = 0;};
myPlayer.onUpdate = function(){};

function playSound(sound) {
	var audioPlayer = document.getElementById("audioPlayer");
	audiofile = "/static/audio/" + sound + ".mp3";

	audioPlayer.SetVariable("method:setUrl", audiofile);
	audioPlayer.SetVariable("method:play", "");
	audioPlayer.SetVariable("enabled", "true");
}

function check_win(idopening) {
	$.get('./rank?r='+idopening,function(data){
		if (data.rank) {
			if (data.rank[0][3] == 0) {
				playSound('vincerefacile');
			}
		}
	});
}
