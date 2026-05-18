import API from './api-config.js';

export default async function handler(req, res) {
    const { action, category_id, series_id } = req.query;
    const BASE = `${API.SERVER}/player_api.php?username=${API.USER}&password=${API.PASS}`;

    try {
        let url;
        if (action === 'categories') {
            url = `${BASE}&action=get_series_categories`;
        } else if (action === 'streams') {
            url = `${BASE}&action=get_series&category_id=${category_id}`;
        } else if (action === 'info') {
            url = `${BASE}&action=get_series_info&series_id=${series_id}`;
        }

        const response = await fetch(url);
        const data = await response.json();

        res.setHeader('Cache-Control', 'public, max-age=3600');
        res.json(data);
    } catch (error) {
        res.status(500).json({ error: 'Erro ao buscar dados' });
    }
}