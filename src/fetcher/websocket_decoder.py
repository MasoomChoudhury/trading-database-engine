from google.protobuf.json_format import MessageToDict
from .market_data_pb2 import FeedResponse

class UpstoxDecoder:
    @staticmethod
    def decode(binary_data):
        """
        Decodes binary market data feed from Upstox.
        Returns a dictionary representation of the FeedResponse.
        """
        try:
            feed_response = FeedResponse()
            feed_response.ParseFromString(binary_data)
            
            # Use MessageToDict for a clean dictionary output
            # preserving_proto_field_name=True ensures we use the names from the .proto file
            return MessageToDict(
                feed_response, 
                preserving_proto_field_name=True,
                always_print_fields_with_no_presence=True
            )
        except Exception as e:
            print(f"❌ Error decoding Protobuf message: {e}")
            return None

    @staticmethod
    def decode_raw(binary_data):
        """
        Returns the raw Protobuf object.
        """
        try:
            feed_response = FeedResponse()
            feed_response.ParseFromString(binary_data)
            return feed_response
        except Exception as e:
            print(f"❌ Error decoding Protobuf message (raw): {e}")
            return None
