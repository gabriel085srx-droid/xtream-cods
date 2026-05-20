export default async function handler(req, res) {
  const url = new URL(req.url);
  const path = url.searchParams.get('path');
  
  if (!path) {
    return res.status(400).json({ error: 'Falta o parâmetro path, carai' });
  }

  const redirectUrl = `https://elitep2p.site/movie/primeapi-vods/217711411/${path}`;

  try {
    // Segue o redirecionamento
    const redirectResponse = await fetch(redirectUrl, { redirect: 'manual' });
    
    let finalUrl;
    
    if (redirectResponse.status === 301 || redirectResponse.status === 302) {
      finalUrl = redirectResponse.headers.get('location');
    } else if (redirectResponse.ok) {
      res.setHeader('Content-Type', redirectResponse.headers.get('content-type') || 'video/mp4');
      redirectResponse.body.pipe(res);
      return;
    } else {
      return res.status(redirectResponse.status).json({ 
        error: `Fonte retornou ${redirectResponse.status}` 
      });
    }

    // Busca o vídeo real do CDN
    const videoResponse = await fetch(finalUrl, {
      headers: req.headers.range ? { Range: req.headers.range } : {}
    });

    if (!videoResponse.ok) {
      return res.status(videoResponse.status).json({ 
        error: `CDN retornou ${videoResponse.status}` 
      });
    }

    res.setHeader('Content-Type', videoResponse.headers.get('content-type') || 'video/mp4');
    res.setHeader('Cache-Control', 'public, max-age=60');
    res.setHeader('Access-Control-Allow-Origin', '*');

    if (videoResponse.headers.get('content-length')) {
      res.setHeader('Content-Length', videoResponse.headers.get('content-length'));
    }
    if (videoResponse.status === 206) {
      res.setHeader('Content-Range', videoResponse.headers.get('content-range'));
      res.status(206);
    }

    videoResponse.body.pipe(res);

  } catch (error) {
    res.status(500).json({ error: error.message });
  }
}