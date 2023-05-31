const sitemap = require('nextjs-sitemap-generator');
const fs = require('fs');
const path = require('path');

sitemap({
    baseUrl: "https://www.sen-tutor.co.uk",
    pagesDirectory: path.resolve(__dirname, '../out/'),
    targetDirectory:path.resolve(__dirname, '../out/'),
    ignoredExtensions: ["js", "map", "json", "xml", "png", "jpg", "jpeg", "svg", "txt"],
    ignoredPaths: ["[fallback]"],
    allowFileExtensions: true
});