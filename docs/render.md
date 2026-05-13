# Deploy on Render

## 1. PostgreSQL

1. In Render dashboard: **New** → **PostgreSQL**.
2. Copy **Internal Database URL** (or External if you need it off-Render).

## 2. API (Web Service)

1. **New** → **Web Service**, connect your Git repo.
2. **Root Directory**: `apps/api`
3. **Runtime**: Python 3
4. **Build Command**:

   ```bash
   pip install -r requirements.txt && alembic upgrade head
   ```

5. **Start Command**:

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

6. **Environment** (example):

   | Key | Value |
   |-----|--------|
   | `DATABASE_URL` | From Postgres instance (Render injects; use same as `Internal Database URL` if manual) |
   | `JWT_SECRET` | Long random string |
   | `OPENAI_API_KEY` | Your OpenAI API key |
   | `CORS_ORIGIN` | Your static site URL, e.g. `https://your-app.onrender.com` |
   | `OPENAI_MODEL` | Optional, default `gpt-4o-mini` |

7. **Health check path**: `/health`

**Note:** If `DATABASE_URL` from Render uses `postgres://`, SQLAlchemy may need `postgresql+psycopg2://`. The app normalizes this on startup.

## 3. Web (Static Site)

1. **New** → **Static Site**, same repo.
2. **Root Directory**: `apps/web`
3. **Build Command**: `npm install && npm run build`
4. **Publish Directory**: `dist`
5. **Environment**:

   | Key | Value |
   |-----|--------|
   | `VITE_API_URL` | Public URL of your API Web Service, e.g. `https://your-api.onrender.com` |

Redeploy the static site after the API URL is known so the build bakes in `VITE_API_URL`.

## 4. Optional: `render.yaml`

You can use [render.yaml](../render.yaml) in the repo root for Blueprint deploys; adjust names and branches as needed.
