const videos = document.querySelectorAll(".video-player");

const observer = new IntersectionObserver((entries) => {

entries.forEach(entry => {

const video = entry.target;

if(entry.isIntersecting){

// pausar todos los demás
videos.forEach(v => {
if(v !== video){
v.pause();
}
});

video.play();

}else{

video.pause();

}

});

},{ threshold: 0.7 });

videos.forEach(video => observer.observe(video));

function deleteVideo(id){

if(confirm("¿Eliminar este video?")){

fetch(`/videos/${id}`,{
method:"DELETE"
})
.then(() => location.reload())

}

}