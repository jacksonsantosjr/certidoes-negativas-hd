const fs = require('fs');
const path = require('path');

console.log('Iniciando build do frontend...');

// 1. Criar pasta public se não existir
if (!fs.existsSync('public')) {
    fs.mkdirSync('public', { recursive: true });
    console.log('Pasta "public" criada com sucesso.');
} else {
    console.log('Pasta "public" já existe.');
}

// 2. Copiar arquivos estáticos para a pasta public
const filesToCopy = ['index.html', 'app.js', 'style.css', 'logo.png'];
filesToCopy.forEach(file => {
    if (fs.existsSync(file)) {
        fs.copyFileSync(file, path.join('public', file));
        console.log(`Copiado: ${file} -> public/${file}`);
    } else {
        console.error(`Aviso: Arquivo ${file} não localizado.`);
    }
});

// 3. Gerar o arquivo config.json com as variáveis de ambiente da Vercel
const config = {
    SUPABASE_URL: process.env.SUPABASE_URL || '',
    SUPABASE_KEY: process.env.SUPABASE_KEY || ''
};

fs.writeFileSync(
    path.join('public', 'config.json'),
    JSON.stringify(config, null, 2)
);
console.log('Gerado: public/config.json com as variáveis de ambiente.');
console.log('Build concluído com sucesso!');
