// ファイルが選択されたときの処理
document.getElementById('imageInput').addEventListener('change', function(event) {
    const file = event.target.files[0]; // 選択されたファイル
    
    if (file) {
        const reader = new FileReader();
        
        reader.onload = function(e) {
            // プレビューエリアに画像を表示
            const preview = document.getElementById('preview');
            preview.innerHTML = `<img src="${e.target.result}" style="max-width: 300px;">`;
        };
        
        reader.readAsDataURL(file); // ファイルを読み込み
    }
});