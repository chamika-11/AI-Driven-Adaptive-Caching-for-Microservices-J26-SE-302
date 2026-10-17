FROM golang:1.27.1-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go build -o /out/app ./cmd/app && \
    CGO_ENABLED=0 go build -o /out/sidecar ./cmd/sidecar && \
    CGO_ENABLED=0 go build -o /out/workflow ./cmd/workflow && \
    CGO_ENABLED=0 go build -o /out/data ./cmd/data && \
    CGO_ENABLED=0 go build -o /out/load ./cmd/load && \
    CGO_ENABLED=0 go build -o /out/validate ./cmd/validate && \
    CGO_ENABLED=0 go build -o /out/smoke ./cmd/smoke
FROM gcr.io/distroless/static-debian12:nonroot@sha256:afa5c872c891853ca7fcf1f12c3edb23f7eeef36189728842dd51042ff57f7ab
COPY --from=build /out/ /
ENTRYPOINT ["/app"]
