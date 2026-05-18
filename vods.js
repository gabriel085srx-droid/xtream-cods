const API = require('../../api-config');

module.exports = async (req, res) => {
    const { action, category_id, vod_id } = req.query;
    const BASE = `${API.SERVER}/player_api.php?username=${API.USER}&password=${API.PASS}`;

    try {
        let url;
        if (action === 'categories') {
            url = `${BASE}&action=get_vod_categories`;
        } else if (action === 'streams') {
            url = `${BASE}&action=get_vod_streams&category_id=${category_id}`;
        } else if (action === 'info') {
            url = `${BASE}&action=get_vod_info&vod_id=${vod_id}`;
        }

        const response = await fetch(url);
        const data = await response.json();

        res.setHeader('Cache-Control', 'public, max-age=3600');
        res.json(data);
    } catch (error) {
        res.status(500).json({ error: 'Erro ao buscar dados' });
    }
};