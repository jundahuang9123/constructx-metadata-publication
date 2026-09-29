FROM node:22-alpine

WORKDIR /app
COPY package.json package-lock.json* ./
COPY apps/publisher-ui/package.json apps/publisher-ui/package.json
RUN npm install

COPY . .
WORKDIR /app/apps/publisher-ui
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

