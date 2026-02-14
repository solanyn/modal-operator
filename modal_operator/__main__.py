import modal_operator.operator  # noqa: F401


def main():
    import kopf

    kopf.run(clusterwide=True)


if __name__ == "__main__":
    main()
