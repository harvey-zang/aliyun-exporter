d={
    "TimeStamp": "2020-02-24T11:13:00Z",
    "Value": {
        "RealTimeSrcCodeProportionData": [
            {
                "Count": 1,
                "Proportion": "0.03990422984836393",
                "Code": "200"
            },
            {
                "Count": 2504,
                "Proportion": "99.92019154030328",
                "Code": "206"
            },
            {
                "Count": 1,
                "Proportion": "0.03990422984836393",
                "Code": "304"
            }
        ],
        "a":"b"
    }
}

for i in d["Value"].items():
    print(i[1])

